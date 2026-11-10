from __future__ import annotations

import asyncio
import json
import os
import queue
import sqlite3
import threading
import uuid
from collections import deque
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.concurrency import iterate_in_threadpool

from .services import PracticeService, GnaniClient, GeminiConversationClient

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "app" / "static"
DB_PATH = Path(os.getenv("DATABASE_PATH", BASE_DIR / "data.sqlite3"))
EVENT_CLIENTS: set[queue.Queue] = set()
EVENT_LOCK = threading.Lock()
EVENT_HISTORY = deque(maxlen=100)
MAX_TRANSCRIPT = 2000

@contextmanager
def db():
    con = sqlite3.connect(DB_PATH, timeout=10)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    con.execute("PRAGMA busy_timeout=10000")
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()

def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with db() as con:
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("""CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY, exercise_id TEXT NOT NULL, target TEXT NOT NULL,
            transcript TEXT NOT NULL, feedback TEXT NOT NULL, created_at TEXT NOT NULL
        )""")
        con.execute("CREATE INDEX IF NOT EXISTS idx_sessions_created_at ON sessions(created_at DESC)")

def publish(event):
    payload = json.dumps(event, separators=(",", ":"))
    with EVENT_LOCK:
        EVENT_HISTORY.append(payload)
        clients = list(EVENT_CLIENTS)
    for client in clients:
        try:
            client.put_nowait(payload)
        except queue.Full:
            pass

def security_headers(response):
    response.headers.update({
        "X-Content-Type-Options": "nosniff",
        "Referrer-Policy": "no-referrer",
        "X-Frame-Options": "DENY",
        "Permissions-Policy": "microphone=(self)",
        "Content-Security-Policy": "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self' ws: wss:; media-src 'self' blob:; base-uri 'none'; frame-ancestors 'none'",
        "Cache-Control": "no-store",
    })
    return response

def provider_status_code(exc):
    seen = set()
    current = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        response = getattr(current, "response", None)
        status_code = getattr(response, "status_code", None)
        if isinstance(status_code, int):
            return status_code
        current = current.__cause__ or current.__context__
    return None

def prisma_connection_error(exc):
    status_code = provider_status_code(exc)
    if status_code == 401:
        return ("Gnani rejected the API key (HTTP 401). Set GNANI_API_KEY to an active "
                "Gnani API Key ID with Prisma access, then restart SpeakWell.")
    if status_code == 403:
        return ("Gnani denied this request (HTTP 403). Check that the API key has Prisma "
                "streaming access for the selected language.")
    return "Prisma streaming connection failed. Check API access and reconnect."

app = FastAPI(title="SpeakWell", version="2.0.0", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
service = PracticeService()
gnani = GnaniClient()
gemini = GeminiConversationClient()

@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    return security_headers(response)

@app.get("/")
async def home():
    return FileResponse(STATIC_DIR / "index.html", headers={"Cache-Control": "no-cache"})

@app.get("/api/health")
async def health():
    return {"ok": True, "app": "SpeakWell", "mode": "live" if gnani.configured else "unavailable"}

@app.get("/api/exercises")
async def exercises():
    return {"exercises": service.exercises()}

@app.get("/api/conversations")
async def conversations():
    return {"conversations": service.conversations()}

@app.get("/api/gnani/status")
async def gnani_status():
    return gnani.status()

@app.get("/api/gemini/status")
async def gemini_status():
    return gemini.status()

@app.get("/api/sessions")
async def sessions():
    with db() as con:
        rows = con.execute("""SELECT id, exercise_id, target, transcript, feedback, created_at
                              FROM sessions ORDER BY created_at DESC LIMIT 50""").fetchall()
    return {"sessions": [{"id": r["id"], "exercise_id": r["exercise_id"], "target": r["target"],
        "transcript": r["transcript"], "feedback": json.loads(r["feedback"]),
        "created_at": r["created_at"]} for r in rows]}

class FeedbackRequest(BaseModel):
    exercise_id: str = Field(min_length=1, max_length=80)
    transcript: str = Field(min_length=1, max_length=MAX_TRANSCRIPT)

class ConversationTurnRequest(BaseModel):
    turn_index: int = Field(ge=0, le=4)
    transcript: str = Field(min_length=1, max_length=MAX_TRANSCRIPT)

class ConversationRequest(BaseModel):
    conversation_id: str = Field(min_length=1, max_length=80)
    turns: list[ConversationTurnRequest] = Field(min_length=1, max_length=5)

class GeminiMessageRequest(BaseModel):
    role: str = Field(pattern="^(user|model)$")
    text: str = Field(min_length=1, max_length=2000)

class GeminiReplyRequest(BaseModel):
    action: str = Field(pattern="^(start|reply)$")
    scenario: str = Field(min_length=1, max_length=80)
    language: str = Field(default="en-IN", max_length=16)
    history: list[GeminiMessageRequest] = Field(default_factory=list, max_length=14)

class GeminiSaveRequest(BaseModel):
    scenario: str = Field(min_length=1, max_length=80)
    history: list[GeminiMessageRequest] = Field(min_length=2, max_length=30)

class SpeakRequest(BaseModel):
    text: str = Field(min_length=1, max_length=1000)
    language: str = Field(default="en-IN", max_length=16)

def save_practice_result(result):
    session_id = str(uuid.uuid4())
    created_at = datetime.now(timezone.utc).isoformat()
    with db() as con:
        con.execute("INSERT INTO sessions VALUES (?, ?, ?, ?, ?, ?)",
            (session_id, result["exercise_id"], result["target"], result["transcript"],
             json.dumps(result["feedback"]), created_at))
    result.update({"session_id": session_id, "created_at": created_at})
    publish({"id": session_id, "exercise_id": result["exercise_id"],
        "target": result["target"], "feedback": result["feedback"],
        "created_at": created_at, "type": "session.created"})
    return result

@app.post("/api/practice/feedback", status_code=201)
async def practice_feedback(body: FeedbackRequest):
    try:
        result = service.feedback(body.model_dump())
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return save_practice_result(result)

@app.post("/api/conversations/complete", status_code=201)
async def complete_conversation(body: ConversationRequest):
    try:
        result = service.conversation_feedback(body.model_dump())
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return save_practice_result(result)

@app.post("/api/gemini/reply")
async def gemini_reply(body: GeminiReplyRequest):
    try:
        history = [message.model_dump() for message in body.history]
        reply, model = await asyncio.to_thread(
            gemini.reply_with_model, body.scenario, body.language, history, body.action == "start"
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except RuntimeError as exc:
        raise HTTPException(502, str(exc))
    return {"reply": reply, "model": model}

@app.post("/api/gemini/reply/stream")
async def gemini_reply_stream(body: GeminiReplyRequest):
    try:
        history = [message.model_dump() for message in body.history]
        chunks, model = await asyncio.to_thread(
            gemini.stream_reply_with_model,
            body.scenario,
            body.language,
            history,
            body.action == "start",
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except RuntimeError as exc:
        raise HTTPException(502, str(exc))

    async def stream():
        try:
            async for text in iterate_in_threadpool(chunks):
                yield f"data: {json.dumps({'type': 'chunk', 'text': text})}\n\n"
            yield f"data: {json.dumps({'type': 'done', 'model': model})}\n\n"
        except RuntimeError as exc:
            yield f"data: {json.dumps({'type': 'error', 'message': str(exc)})}\n\n"

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
    )

@app.post("/api/gemini/save", status_code=201)
async def save_gemini_conversation(body: GeminiSaveRequest):
    history = [message.model_dump() for message in body.history]
    if history[-1]["role"] != "model" or len(history) % 2:
        raise HTTPException(400, "Finish the conversation before saving it")
    if sum(message["role"] == "user" for message in history) < 2:
        raise HTTPException(400, "Have at least one conversation turn before saving")
    if any(message["role"] == history[index - 1]["role"]
           for index, message in enumerate(history) if index):
        raise HTTPException(400, "Conversation messages must alternate between user and assistant")
    transcript = "\n".join(
        f"{'You' if message['role'] == 'user' else 'Gemini'}: {message['text']}"
        for message in history
    )
    if len(transcript) > 10000:
        raise HTTPException(400, "Conversation is too long to save")
    scenario_title = "Open conversation" if body.scenario == gemini.OPEN_SCENARIO else next(
        (item["title"] for item in service.conversations() if item["id"] == body.scenario), None
    )
    if not scenario_title:
        raise HTTPException(400, "Choose a valid conversation scenario")
    result = {
        "exercise_id": "gemini-conversation",
        "target": f"AI conversation · {scenario_title}",
        "transcript": transcript,
        "feedback": {
            "activity_type": "ai_conversation",
            "completed_turns": sum(message["role"] == "user" for message in history) - 1,
            "message": "Conversation saved for your reflection.",
            "disclaimer": "AI replies are generated for practice. They do not measure pronunciation or provide clinical advice.",
        },
    }
    return save_practice_result(result)

@app.post("/api/gnani/speak")
async def speak(body: SpeakRequest):
    try:
        audio, content_type = await asyncio.to_thread(gnani.synthesize, body.text, body.language)
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(502 if isinstance(exc, RuntimeError) else 400, str(exc))
    from fastapi.responses import Response
    return Response(audio, media_type=content_type if content_type.startswith("audio/") else "audio/wav",
                    headers={"Cache-Control": "no-store"})

@app.get("/api/events")
async def events():
    async def stream():
        q = queue.Queue(maxsize=50)
        with EVENT_LOCK:
            EVENT_CLIENTS.add(q)
            history = list(EVENT_HISTORY)
        try:
            for item in history[-20:]:
                yield f"event: session\ndata: {item}\n\n"
            while True:
                try:
                    item = await asyncio.to_thread(q.get, True, 15)
                    yield f"event: session\ndata: {item}\n\n"
                except queue.Empty:
                    yield ": keep-alive\n\n"
        finally:
            with EVENT_LOCK:
                EVENT_CLIENTS.discard(q)
    return StreamingResponse(stream(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"})

@app.websocket("/ws/prisma")
async def prisma_stream(websocket: WebSocket):
    # Browser connects only to same-origin app; provider key remains server-side.
    origin = websocket.headers.get("origin")
    host = websocket.headers.get("host", "")
    if origin and urlparse(origin).netloc != host:
        await websocket.close(code=1008, reason="Origin not allowed")
        return
    if not gnani.configured:
        await websocket.accept()
        await websocket.send_json({"type": "error", "message": "Gnani API key is not configured. Add it to .env and restart."})
        await websocket.close(code=1011)
        return
    await websocket.accept()
    stream = None
    receive_task = None
    try:
        from gnani.stt import GnaniSTTStreamClient, StreamTranscriptEvent, StreamProcessingEvent, StreamErrorEvent
        language = websocket.query_params.get("language", "en-IN")
        allowed = GnaniSTTStreamClient.supported_languages()
        if language not in allowed:
            await websocket.send_json({"type": "error", "message": "Unsupported language selection."})
            await websocket.close(code=1008)
            return
        stream = GnaniSTTStreamClient(api_key=gnani.api_key, language_code=language,
            sample_rate=16000)
        await stream.connect()
        await websocket.send_json({"type": "ready", "provider": "Gnani Prisma v3.0", "sample_rate": 16000, "frame_bytes": 1024})

        async def forward_events():
            async for event in stream:
                if isinstance(event, StreamTranscriptEvent):
                    await websocket.send_json({"type": "transcript", "text": event.text,
                        "latency_ms": getattr(event, "latency", None),
                        "language": getattr(event, "detected_language_code", None),
                        "segment_index": getattr(event, "segment_index", None)})
                elif isinstance(event, StreamProcessingEvent):
                    await websocket.send_json({"type": "processing"})
                elif isinstance(event, StreamErrorEvent):
                    await websocket.send_json({"type": "error", "message": "Gnani reported a streaming error."})
        receive_task = asyncio.create_task(forward_events())
        total_bytes = 0
        while True:
            message = await websocket.receive()
            if message["type"] == "websocket.disconnect":
                break
            if message.get("bytes") is not None:
                frame = message["bytes"]
                if len(frame) != 1024:
                    await websocket.send_json({"type": "error", "message": "Audio frame must be exactly 1,024 bytes (16 kHz mono PCM16)."})
                    continue
                total_bytes += len(frame)
                if total_bytes > 16_000 * 2 * 60:
                    await websocket.send_json({"type": "error", "message": "Session reached the 60-second audio limit."})
                    break
                await stream.send_audio(frame)
            elif message.get("text"):
                command = json.loads(message["text"])
                if command.get("type") == "stop":
                    break
        if stream:
            await stream.close()
        if receive_task:
            try:
                await asyncio.wait_for(receive_task, timeout=2)
            except (asyncio.TimeoutError, Exception):
                receive_task.cancel()
        await websocket.send_json({"type": "complete"})
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        try:
            await websocket.send_json({"type": "error", "message": prisma_connection_error(exc)})
            await websocket.close(code=1011)
        except Exception:
            pass
    finally:
        if receive_task and not receive_task.done():
            receive_task.cancel()
        if stream:
            try:
                await stream.close()
            except Exception:
                pass

@app.on_event("startup")
async def startup():
    init_db()

def main():
    import uvicorn
    uvicorn.run(app, host=os.getenv("HOST", "127.0.0.1"),
                port=int(os.getenv("PORT", "8000")), reload=False)

if __name__ == "__main__":
    main()

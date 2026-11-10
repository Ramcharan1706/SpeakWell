import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
from app import server
from app.services import GeminiConversationClient

class ServerIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        server.DB_PATH = Path(self.tmp.name) / "test.sqlite3"
        server.EVENT_HISTORY.clear()
        server.init_db()
        self.client = TestClient(server.app)

    def tearDown(self):
        self.client.close()
        self.tmp.cleanup()

    def test_health_and_security_headers(self):
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])
        self.assertEqual(response.headers["x-content-type-options"], "nosniff")
        self.assertEqual(response.headers["x-frame-options"], "DENY")

    def test_static_homepage_served(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("SpeakWell", response.text)
        self.assertNotIn("Browser voice type", response.text)
        self.assertIn('<option value="en-IN" selected>', response.text)
        self.assertNotIn("indic-auto", response.text)
        self.assertIn("Talk with Gemini", response.text)
        self.assertEqual(self.client.get("/static/app.js").status_code, 200)
        self.assertEqual(self.client.get("/static/styles.css").status_code, 200)

    def test_exercise_api(self):
        self.assertGreaterEqual(len(self.client.get("/api/exercises").json()["exercises"]), 4)

    def test_provider_status_does_not_expose_api_key(self):
        original = server.gnani
        class WithKey:
            configured = True
            api_key = "private-test-key"

            def status(self):
                return {"configured": self.configured, "mode": "live"}

        server.gnani = WithKey()
        try:
            response = self.client.get("/api/gnani/status")
        finally:
            server.gnani = original

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("private-test-key", response.text)
        self.assertTrue(response.json()["configured"])

    def test_gemini_status_reports_configuration_without_exposing_key(self):
        original = server.gemini

        class FakeGemini:
            model = "gemini-3.8-flash"

            def status(self):
                return {"configured": True, "model": self.model, "message": "Ready"}

        server.gemini = FakeGemini()
        try:
            response = self.client.get("/api/gemini/status")
        finally:
            server.gemini = original

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["configured"])
        self.assertNotIn("private-test-key", response.text)

    def test_gemini_reply_forwards_the_conversation_context(self):
        original = server.gemini

        class FakeGemini:
            model = "gemini-3.8-flash"

            def reply_with_model(self, scenario, language, history, start=False):
                self.args = (scenario, language, history, start)
                return "What would you like to order?", "gemini-2.5-flash"

        fake = FakeGemini()
        server.gemini = fake
        try:
            response = self.client.post("/api/gemini/reply", json={
                "action": "reply",
                "scenario": "cafe-order",
                "language": "en-IN",
                "history": [
                    {"role": "user", "text": "Let's practise a cafe conversation."},
                    {"role": "model", "text": "Welcome!"},
                    {"role": "user", "text": "Could I have some tea?"},
                ],
            })
        finally:
            server.gemini = original

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"reply": "What would you like to order?", "model": "gemini-2.5-flash"})
        self.assertEqual(fake.args[0], "cafe-order")
        self.assertEqual(fake.args[2][-1]["text"], "Could I have some tea?")

    def test_gemini_stream_endpoint_sends_reply_chunks(self):
        original = server.gemini

        class FakeGemini:
            def stream_reply_with_model(self, scenario, language, history, start=False):
                self.args = (scenario, language, history, start)
                return iter(["Hello ", "there!"]), "gemini-2.5-flash"

        fake = FakeGemini()
        server.gemini = fake
        try:
            response = self.client.post("/api/gemini/reply/stream", json={
                "action": "start",
                "scenario": "open-conversation",
                "language": "en-IN",
                "history": [],
            })
        finally:
            server.gemini = original

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"], "text/event-stream; charset=utf-8")
        self.assertIn('"type": "chunk", "text": "Hello "', response.text)
        self.assertIn('"type": "chunk", "text": "there!"', response.text)
        self.assertIn('"type": "done", "model": "gemini-2.5-flash"', response.text)
        self.assertEqual(fake.args, ("open-conversation", "en-IN", [], True))

    def test_gemini_reply_refuses_invalid_message_history(self):
        original = server.gemini
        server.gemini = GeminiConversationClient(api_key="test-key")
        try:
            response = self.client.post("/api/gemini/reply", json={
                "action": "reply",
                "scenario": "cafe-order",
                "history": [
                    {"role": "user", "text": "First"},
                    {"role": "user", "text": "Second"},
                ],
            })
        finally:
            server.gemini = original

        self.assertEqual(response.status_code, 400)
        self.assertIn("alternate", response.json()["detail"])

    def test_gemini_reply_reports_missing_key_without_provider_call(self):
        original = server.gemini
        server.gemini = GeminiConversationClient(api_key="")
        try:
            response = self.client.post("/api/gemini/reply", json={
                "action": "start",
                "scenario": "open-conversation",
                "history": [],
            })
        finally:
            server.gemini = original

        self.assertEqual(response.status_code, 502)
        self.assertIn("GEMINI_API_KEY", response.json()["detail"])

    def test_create_session_persists_and_returns_201(self):
        exercise = server.service.exercises()[0]
        response = self.client.post("/api/practice/feedback",
            json={"exercise_id": exercise["id"], "transcript": exercise["target"]})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["feedback"]["prompt_word_overlap_percent"], 100)
        sessions = self.client.get("/api/sessions").json()["sessions"]
        self.assertEqual(len(sessions), 1)

    def test_speak_returns_audio_from_provider(self):
        with patch.object(server.gnani, "synthesize", return_value=(b"RIFF-test-audio", "audio/wav")):
            response = self.client.post("/api/gnani/speak",
                json={"text": "Test prompt", "language": "en-IN"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"RIFF-test-audio")
        self.assertEqual(response.headers["content-type"], "audio/wav")

    def test_speak_reports_provider_failure(self):
        with patch.object(server.gnani, "synthesize", side_effect=RuntimeError("Provider unavailable")):
            response = self.client.post("/api/gnani/speak",
                json={"text": "Test prompt", "language": "en-IN"})

        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json()["detail"], "Provider unavailable")

    def test_speak_rejects_empty_text(self):
        response = self.client.post("/api/gnani/speak",
            json={"text": "", "language": "en-IN"})

        self.assertEqual(response.status_code, 422)

    def test_invalid_feedback_is_rejected(self):
        response = self.client.post("/api/practice/feedback",
            json={"exercise_id":"bad", "transcript":"hello"})
        self.assertEqual(response.status_code, 400)

    def test_unconfigured_live_websocket_refuses_without_demo(self):
        original = server.gnani
        class NoKey:
            configured = False
            api_key = ""
        server.gnani = NoKey()
        try:
            with self.client.websocket_connect("/ws/prisma") as ws:
                message = ws.receive_json()
                self.assertEqual(message["type"], "error")
                self.assertIn("not configured", message["message"])
        finally:
            server.gnani = original

    def test_live_websocket_rejects_foreign_origin(self):
        with self.assertRaises(WebSocketDisconnect):
            with self.client.websocket_connect(
                "/ws/prisma", headers={"origin": "http://attacker.example"}
            ):
                pass

    def test_configured_live_websocket_uses_supported_sdk_arguments(self):
        original = server.gnani
        class WithKey:
            configured = True
            api_key = "test-key"

        class FakeStream:
            async def connect(self):
                pass

            async def close(self):
                pass

            def __aiter__(self):
                return self

            async def __anext__(self):
                raise StopAsyncIteration

        server.gnani = WithKey()
        try:
            with patch("gnani.stt.GnaniSTTStreamClient") as stream_factory:
                stream_factory.supported_languages.return_value = {"en-IN": "English (India)"}
                stream_factory.return_value = FakeStream()
                with self.client.websocket_connect("/ws/prisma") as ws:
                    self.assertEqual(ws.receive_json()["type"], "ready")
                    ws.send_json({"type": "stop"})
                    self.assertEqual(ws.receive_json()["type"], "complete")
                stream_factory.assert_called_once_with(
                    api_key="test-key", language_code="en-IN", sample_rate=16000
                )
        finally:
            server.gnani = original

    def test_live_websocket_reports_upstream_authentication_failure(self):
        original = server.gnani

        class WithKey:
            configured = True
            api_key = "test-key"

        class ProviderResponse:
            status_code = 401

        class ProviderAuthenticationError(Exception):
            response = ProviderResponse()

        class FakeStream:
            async def connect(self):
                try:
                    raise ProviderAuthenticationError()
                except ProviderAuthenticationError as provider_error:
                    raise RuntimeError("SDK connection failed") from provider_error

        server.gnani = WithKey()
        try:
            with patch("gnani.stt.GnaniSTTStreamClient") as stream_factory:
                stream_factory.supported_languages.return_value = {"en-IN": "English (India)"}
                stream_factory.return_value = FakeStream()
                with self.client.websocket_connect("/ws/prisma?language=en-IN") as ws:
                    error = ws.receive_json()
                    self.assertEqual(error["type"], "error")
                    self.assertIn("HTTP 401", error["message"])
                    self.assertIn("Gnani API Key ID", error["message"])
                    self.assertNotIn("test-key", error["message"])
        finally:
            server.gnani = original

    def test_auto_detect_language_is_rejected_when_sdk_does_not_support_it(self):
        original = server.gnani
        class WithKey:
            configured = True
            api_key = "test-key"

        server.gnani = WithKey()
        try:
            with patch("gnani.stt.GnaniSTTStreamClient") as stream_factory:
                stream_factory.supported_languages.return_value = {"en-IN": "English (India)"}
                with self.client.websocket_connect("/ws/prisma?language=indic-auto") as ws:
                    message = ws.receive_json()
                    self.assertEqual(message["type"], "error")
                    self.assertEqual(message["message"], "Unsupported language selection.")
                stream_factory.assert_not_called()
        finally:
            server.gnani = original

    def test_invalid_audio_frame_is_rejected_without_forwarding(self):
        original = server.gnani
        class WithKey:
            configured = True
            api_key = "test-key"

        class FakeStream:
            async def connect(self):
                pass

            async def close(self):
                pass

            async def send_audio(self, frame):
                raise AssertionError("Invalid frame reached provider")

            def __aiter__(self):
                return self

            async def __anext__(self):
                raise StopAsyncIteration

        server.gnani = WithKey()
        try:
            with patch("gnani.stt.GnaniSTTStreamClient") as stream_factory:
                stream_factory.supported_languages.return_value = {"en-IN": "English (India)"}
                stream_factory.return_value = FakeStream()
                with self.client.websocket_connect("/ws/prisma?language=en-IN") as ws:
                    self.assertEqual(ws.receive_json()["type"], "ready")
                    ws.send_bytes(bytes(128))
                    error = ws.receive_json()
                    self.assertEqual(error["type"], "error")
                    self.assertIn("exactly 1,024 bytes", error["message"])
                    ws.send_json({"type": "stop"})
                    self.assertEqual(ws.receive_json()["type"], "complete")
        finally:
            server.gnani = original

    def test_events_stream_replays_recent_sessions(self):
        expected = {"id": "test-session", "type": "session.created"}
        server.EVENT_HISTORY.append(json.dumps(expected))

        async def first_event():
            response = await server.events()
            iterator = response.body_iterator
            try:
                return await anext(iterator)
            finally:
                await iterator.aclose()

        chunk = asyncio.run(first_event())

        self.assertIn("event: session", chunk)
        self.assertIn(json.dumps(expected), chunk)

    def test_unknown_route(self):
        self.assertEqual(self.client.get("/missing").status_code, 404)

if __name__ == "__main__":
    unittest.main()

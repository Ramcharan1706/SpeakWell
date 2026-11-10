# SpeakWell — live Gnani speech-practice studio

SpeakWell is a local speech-practice application. Its microphone workflow streams live 16 kHz mono PCM audio from the browser to **Gnani Prisma v3.0 over WebSocket**. Completed transcript segments are returned while the session is running. The API key stays on the Python server.

This is a practice aid, not a medical device, diagnosis, pronunciation grader, or replacement for a qualified speech-language professional.

## What is genuinely implemented

| Capability | Implementation | Verification status |
|---|---|---|
| Live speech-to-text | Gnani `GnaniSTTStreamClient`, Prisma v3.0 WebSocket | Protocol integration implemented; live account test still required |
| Browser audio | 16 kHz mono PCM16, 512 samples / 1,024 bytes per frame | Client frame construction implemented; browser hardware test required |
| Live transcript | WebSocket event forwarding to the UI | Local backend contract tested; provider event test requires credentials |
| Speech playback | Gnani Timbre v2.5 REST inference | Direct provider request; not streaming playback |
| Practice feedback | Local prompt-word overlap calculation | Tested; not pronunciation assessment |
| AI conversation | Gemini replies to the selected scenario and conversation history; reply text streams into the chat | Live provider requires `GEMINI_API_KEY`; mocked request and conversation workflow are tested |
| Voice conversation | Gnani Prisma transcribes each spoken turn; Gemini replies; Gnani Timbre speaks the reply | Turn-by-turn voice flow, not full-duplex audio streaming |
| Guided role-play | Six scripted, three-turn everyday scenarios | Optional structured practice separate from the adaptive Gemini conversation |
| Session history | SQLite WAL | Local API persistence tested |
| Cross-client updates | Server-Sent Events for saved sessions | Local event architecture retained; not multi-instance |

There is **no demo AI response, no browser speech-recognition fallback, and no browser TTS fallback**. Gemini and Gnani keys remain on the server. If a key is absent or a provider fails, the app reports an error rather than inventing a result.

## Technology

- Python 3.10+
- FastAPI + Uvicorn for async HTTP and WebSocket handling
- `gnani-vachana==0.8.1` official Gnani Vachana SDK for Prisma streaming and Timbre synthesis
- Gemini `streamGenerateContent` REST API for contextual, short conversation turns
- SQLite with WAL for local session history
- Vanilla JavaScript and Web Audio API; no frontend build chain

FastAPI is used because this product needs async WebSockets. A frontend framework migration was intentionally avoided: it would add complexity without improving the core microphone-to-transcript path.

## Setup

1. Revoke any API key previously pasted into a chat or shared location. Create an active **Gnani API Key ID** in your Gnani account, with access to Prisma streaming and Timbre synthesis.
2. Extract this ZIP and open the project folder in a terminal.
3. Create a virtual environment and install dependencies:

   **Windows**
   ```powershell
   py -m venv .venv
   .venv\Scripts\activate
   py -m pip install -r requirements.txt
   Copy-Item .env.example .env
   ```

   **macOS / Linux**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   cp .env.example .env
   ```

4. Put your new key in `.env`:
   ```dotenv
   GNANI_API_KEY=YOUR_GNANI_API_KEY_ID
   GEMINI_API_KEY=YOUR_GEMINI_API_KEY
   GEMINI_MODEL=gemini-2.5-flash
   GEMINI_FALLBACK_MODEL=gemini-3.8-flash
   GNANI_STT_MODEL=prisma-v3.0
   GNANI_TTS_MODEL=timbre-v2.5
   GNANI_TTS_VOICE=Nalini
   HOST=127.0.0.1
   PORT=8000
   ```

5. Start the app:
   ```bash
   python -m app.server
   ```
6. Open `http://127.0.0.1:8000`. Microphone access works on localhost in modern browsers.

Do not expose this local prototype to the public internet. `.env` is excluded from version control. Never place API keys in browser JavaScript or screenshots.
Gemini requests use your Google AI account and may be subject to its quotas or charges. Review your account limits before extended practice.

## Live practice

### Back-and-forth voice conversation

1. Select **Talk with Gemini**, choose a scenario, and start the conversation. Gemini opens with a natural prompt.
2. Speak using **Speak**. Browser audio streams to Gnani Prisma; when you stop the microphone, completed transcript segments appear in the message box. You can also type instead.
3. Send your message. Gemini receives the scenario and recent turns and responds naturally. Reply text appears as Gemini generates it; Gnani Timbre synthesizes and plays the complete reply in the background so you can prepare your next turn without waiting for audio. Continue for up to six learner turns per conversation.
4. Choose **End & save** to store the transcript and turn count in Progress. It is not graded.

This is real, contextual back-and-forth at the end of each spoken turn, but it is a **cascaded** voice design: audio → Gnani transcription → Gemini text reply → Gnani speech synthesis. It is not simultaneous full-duplex audio: Gemini reply text streams into the chat, while Gnani speech is synthesized as one complete audio response. User audio is sent to Gnani; transcripts and conversation context are sent to Google Gemini; Gemini's reply text is sent to Gnani for speech. The browser starts microphone permission, audio setup, and the Prisma connection concurrently, so startup still depends on browser permission and the upstream connection. Gemini is capped at 64 output tokens to keep spoken replies short. The first call verifies account access; a configured key alone does not guarantee the chosen model is enabled. Network failures and provider 5xx errors get one fallback attempt; HTTP 429 rate limits return immediately instead of waiting on a second model.

### Guided speech exercises

Choose a speech exercise or one of the six scripted role-plays. Select a supported language and type or use **Start live Prisma**. Prisma emits completed transcript segments rather than character-by-character partials. Timbre playback is a single REST response. Scripted role-play lines do not adapt to the learner's response.

Conversation partners use fixed, authored prompts; the next line does not adapt to what you say. Role-play transcripts are saved together and deliberately do not receive a word-overlap or conversational-quality score.

The browser captures PCM16 audio at 16 kHz and sends 1,024-byte frames (512 mono samples) through the app's WebSocket gateway. Gnani's SDK handles the authenticated upstream WebSocket connection. The backend enforces frame size and a 60-second audio cap.

## Tests

```bash
python -m unittest discover -s tests -v
python -m compileall -q app tests
node --check app/static/app.js
```

Unit and API tests do not prove that a specific API key has access. Live provider tests require valid keys, enabled models, available account quota, and network access. Gemini HTTP 429 responses indicate provider rate limiting or quota exhaustion; SpeakWell reports these immediately and does not retry them automatically. Wait for quota to reset or review the Google AI project quota and billing settings. Dependency installation was not needed for this validation because the project manifests were unchanged.

## Important limitations

- No real-time Evon integration.
- Gemini conversation access is unavailable until `GEMINI_API_KEY` is configured and the account/model access is verified.
- Timbre currently uses direct REST synthesis; the output is not progressively streamed.
- Prisma emits completed segments/events; the UI does not claim phoneme-level or character-level streaming.
- Prompt-word overlap measures transcript text matching only. It does not measure pronunciation, articulation, fluency, or clinical progress.
- Guided conversations are scripted practice scenarios, not a responsive AI companion; their transcripts are not evaluated for correctness.
- No user accounts, per-user authorization, multi-tenant data isolation, CSRF workflow, production rate limiting, or managed secret store. Keep the server bound to loopback for this prototype.
- SSE fanout is in-process. Multi-worker deployment requires a shared event broker.
- No formal browser matrix, accessibility conformance audit, load test, or production deployment validation has been completed.

## API

- `GET /api/health`
- `GET /api/exercises`
- `GET /api/conversations`
- `GET /api/gemini/status`
- `POST /api/gemini/reply` — contextual Gemini conversation turn
- `POST /api/gemini/reply/stream` — stream Gemini reply text as it is generated
- `POST /api/gemini/save` — save a completed AI conversation
- `GET /api/gnani/status`
- `POST /api/gnani/speak` — direct Timbre REST synthesis
- `POST /api/practice/feedback`
- `POST /api/conversations/complete` — save all ordered role-play turns
- `GET /api/sessions`
- `GET /api/events` — SSE session updates
- `WS /ws/prisma?language=...` — live Prisma WebSocket proxy

## Official provider references

- [Gnani Vachana SDK](https://github.com/Gnani-AI-Mintlify/Gnani-Vachana)
- [Gnani Prisma WebSocket protocol](https://docs.gnani.ai/api/STT/stt-websocket)
- [Gnani Timbre WebSocket documentation](https://docs.gnani.ai/api/TTS/tts-websocket)
- [Gemini API text generation](https://ai.google.dev/gemini-api/docs/text-generation)

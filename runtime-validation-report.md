# Runtime Validation Report

**Generated:** 2026-11-09  
**Target:** SpeakWell at `http://127.0.0.1:8765`

## Summary

| Step | Status | Exit code | Details |
|---|---|---:|---|
| Startup | PASS | 0 | Updated server started on port 8765; health, home, Gemini status, and conversation endpoints responded. |
| Python tests | PASS | 0 | 48 tests across three test files. |
| Syntax | PASS | 0 | `compileall` for app/tests and `node --check` for the frontend. |
| Live Prisma STT | PASS | 0 | Four generated PCM16 speech samples streamed through the app; all four returned transcript events and completed. |
| Live Gnani TTS | PASS | 0 | `/api/gnani/speak` returned `200 audio/wav` for a live Gemini reply (599,084 bytes). |
| Gemini conversation | PARTIAL | n/a | Live opening/follow-up succeeded earlier on `gemini-2.5-flash`; current account requests are returning HTTP 429. Rate limits now surface immediately without spending time on a second model. |
| Browser workflow | PASS | 0 | Shared browser verified Prisma WebSocket startup in 3.1–4.0s using synthetic silent audio, then clean stop. Delayed-TTS test confirmed the reply and next-turn input stay usable while speech is pending. |
| Performance | PARTIAL | n/a | Before optimization, Gemini fallback round-trips measured 6.0s (opening) and 4.0s (follow-up); TTS measured 2.9s. Local APIs remained under 15ms. Mic permission, audio context, and Prisma connection now start concurrently. Fresh Gemini timing is blocked by HTTP 429. |
| Responsive UI | PASS | 0 | AI conversation card rendered without horizontal overflow at a narrow viewport in the prior shared-browser check. |

**Overall:** PASS for application tests and the synthetic-audio Prisma browser path; PARTIAL for current live Gemini performance while the provider account is rate-limited. Physical-microphone capture and browser save remain unverified in this run.

## Test evidence

- `python -m unittest discover -s tests -v`: 48 passed, 0 failed.
- `python -m compileall -q app tests`: passed.
- `node --check app/static/app.js`: passed.
- Live `/api/gemini/reply` start and follow-up succeeded with `gemini-2.5-flash` after `gemini-3.8-flash` returned HTTP 503 (temporary provider overload).
- Live `/api/gnani/speak` synthesized the follow-up response as WAV audio.
- Shared-browser flow rendered a live Gemini cafe greeting, accepted a typed learner turn, displayed the contextual response, and completed Gnani speech synthesis.
- Four live samples: clear speech, R sound, sentence flow, and everyday conversation; all completed with transcripts.
- Live TTS response: `200`, `audio/wav`.
- `GET /api/conversations`: six scenarios, each with three turns.
- Completed a three-turn cafe role-play in the browser; it appeared in SQLite-backed history without a fabricated overlap score.
- Gemini client sends the selected scenario and alternating user/model history to the documented `generateContent` REST API; API-key header and sanitized provider errors are covered by mocked tests.
- Browser mocked-provider check completed a Gemini conversation turn and saved it to the Progress list. Gnani TTS failure retained the visible text reply and surfaced a clear notice.
- `GET /api/gemini/status` reports a configured primary model. The new bounded fallback retries once on network failures, HTTP 429, and HTTP 5xx; authentication and other non-retryable failures are not retried.
- Docker daemon is unavailable: Docker could not connect to `npipe:////./pipe/dockerDesktopLinuxEngine`; tests used isolated SQLite databases.
- The standalone `npx playwright install --with-deps chromium` attempt downloaded Chromium and FFmpeg but stalled while downloading the headless shell. The shared browser was used for live UI validation; local headless Playwright and physical-microphone testing remain unavailable.
- A physical microphone/hardware matrix was not tested; live STT was verified with generated PCM16 speech samples.
- Performance optimization: `gemini-2.5-flash` is now the primary model because `gemini-3.8-flash` previously returned 503 and required a fallback. The local `.env` was updated without displaying credentials. Live performance timing of the new primary could not be completed because both model requests returned HTTP 429 during the follow-up benchmark. The browser was separately tested with controlled slow TTS: the text appeared and the next-turn send button enabled before synthesis completed.
- Prisma start was reworked to initialize microphone permission, audio context, and the provider WebSocket concurrently. Shared-browser tests used a silent synthetic MediaStream (no physical microphone audio), reached the ready state in 3.1–4.0 seconds, and stopped cleanly. The remaining startup wait is the upstream Gnani connection.
- Gemini output is capped at 64 tokens; HTTP 429 now returns a clear quota/rate-limit message rather than delaying the response with a fallback attempt.
- The test runner emits a non-blocking Starlette `TestClient` deprecation warning.

## Coverage

- `tests/test_server.py`: HTTP endpoints, security headers, static assets, Gemini status/reply validation, TTS responses, persistence, SSE replay, WebSocket origin/language/frame validation, and provider readiness.
- `tests/test_services.py`: Gemini REST request and context validation, provider error sanitization, exercise feedback, and Gnani client configuration/TTS behavior.
- `tests/test_workflows.py`: saved-practice, scripted conversation, and AI conversation persistence flows.

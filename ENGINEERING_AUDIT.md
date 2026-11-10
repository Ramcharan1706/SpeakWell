# SpeakWell engineering audit — final build

## Baseline findings
- Synchronous `http.server` backend was not appropriate for full-duplex audio streaming.
- Speech recognition uploaded a complete WAV after the user pressed Stop; it was not live streaming.
- UI exposed browser speech recognition and local scripted companion behavior.
- Provider status could imply that a configured key meant successful connectivity.
- No real-time upstream Prisma WebSocket integration existed.
- Timbre was a single-response REST request.
- Text-overlap feedback could be misunderstood as speech quality evaluation.

## Implemented changes
- Migrated backend routing to FastAPI/Starlette ASGI and Uvicorn.
- Added `WS /ws/prisma` using the official `gnani-vachana==0.8.1` SDK's `GnaniSTTStreamClient`.
- Added same-origin WebSocket Origin validation, strict 1,024-byte PCM frame validation, supported-language allowlist, 60-second per-session audio ceiling, and server-side API key use.
- Browser microphone now sends mono PCM16 frames at 16 kHz in real time; the backend relays completed Prisma transcript segments to the browser.
- Removed browser SpeechRecognition fallback and local scripted companion feature.
- Removed demo mode; missing credentials are reported as unavailable and live websocket connections are refused with a clear error.
- Kept Timbre on direct REST synthesis; it is not advertised as streamed playback.
- Preserved exercise selection, local text-overlap feedback, SQLite session history, and SSE updates.
- Added explicit README limitations and environment configuration.

## Technology decision
FastAPI + Uvicorn is appropriate for async WebSocket handling without forcing a frontend rewrite. The official Gnani Python SDK is used rather than reimplementing the provider handshake and event parsing. Vanilla JS remains adequate for this small UI. SQLite remains suitable for local single-user practice; PostgreSQL and a shared event broker are deferred until multi-user hosting is required.

## Verification performed in this build environment
- Existing test baseline: 20/20 tests passed before the ASGI migration.
- Updated tests: API persistence, validation, security headers, static UI, missing-key websocket refusal, service validation.
- Python compilation and JavaScript syntax checks are required before packaging.
- Provider package install and live Gnani requests were not possible in this environment because package-index/network access was unavailable.
- No live provider credential was used or embedded.
- No browser automation or physical microphone test was performed.

## Remaining production blockers
1. Run a live Prisma account smoke test on the target machine.
2. Test microphone capture across Chrome, Edge, Safari and mobile browsers.
3. Add authentication and per-user data isolation before any multi-user deployment.
4. Add request/session rate limits and abuse controls.
5. Use managed secrets and HTTPS behind a hardened reverse proxy for hosted deployments.
6. Add a shared event broker if running multiple workers.
7. Implement and verify Timbre WebSocket chunk playback if streamed TTS is required.
8. Conduct WCAG 2.2 AA, load, and browser end-to-end testing.

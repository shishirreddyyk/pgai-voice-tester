# Project rules — read before every task

Build strictly phase-by-phase per IMPLEMENTATION_ROADMAP.md.
Never start a phase you were not explicitly asked to start.
After finishing a phase, stop and wait for me to validate before continuing.

## Invariants — never violate, any phase
1. Only ever dial +18054398008. Hardcode an allowlist; the dialer raises if asked to call anything else. One caller ID for all calls.
2. g711_ulaw (PCMU) for BOTH input and output audio on the Realtime session. No transcoding.
3. Listen-first: the bot must NOT speak first. The agent answers and greets; the bot responds after. Do NOT send an initial response.create on session start.
4. Always tear down websockets on hangup and cap call duration (~4 min hard limit).
5. Never commit secrets. .env is gitignored; only .env.example is committed.
6. Roles: in the Realtime session the AGENT is the `user` (input audio), our BOT is the `assistant` (output). Never invert this.

Stack: Twilio Programmable Voice + Media Streams (outbound), OpenAI Realtime API speech-to-speech (model gpt-realtime), FastAPI + websockets + uvicorn, Python 3.11+, ngrok tunnel, ffmpeg.

# PGAI Voice-Agent Evaluation Harness

An automated red-team / evaluation harness that calls Pretty Good AI's test agent
(`+1-805-439-8008`), runs scenario-driven patient conversations, records and
transcribes them, and produces a founder-quality evaluation report. The voice bot
is the instrument; the evaluation is the product.

> Build status: **Phase 0** (skeleton + ground truth). Call logic lands in Phase 1.

## Stack
- **Telephony:** Twilio Programmable Voice + Media Streams (outbound, WebSocket audio)
- **Brain:** OpenAI Realtime API (speech-to-speech), model `gpt-realtime`
- **Server:** FastAPI + `websockets` + `uvicorn`, Python 3.11+
- **Tunnel:** ngrok (or Cloudflare Tunnel) so Twilio can reach your `wss://` endpoint
- **Audio:** ffmpeg

## Invariants (never violated, any phase)
1. Only ever dial `+1-805-439-8008` — enforced by a hardcoded allowlist.
2. `g711_ulaw` (PCMU) for both input and output audio. No transcoding.
3. Listen-first: the bot does not speak first; it responds after the agent greets.
4. Always tear down websockets on hangup; hard cap call duration (~4 min).
5. Never commit secrets — `.env` is gitignored; only `.env.example` is committed.
6. Roles: agent = `user` (input), our bot = `assistant` (output). Never inverted.

## Prerequisites (set up by hand before Phase 1)
1. **Python 3.11+** and **ffmpeg** (`ffmpeg -version` works).
2. **Twilio** — a *paid/upgraded* account (not trial), a phone number, SID + auth token.
3. **OpenAI API key** with **Realtime API access**.
4. **ngrok** (or Cloudflare Tunnel) for a stable public `https`/`wss` domain.
5. Fill in [`data/practice_info.md`](data/practice_info.md) with real practice data.

## Setup
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env        # then fill in your secrets
python -c "from src.config import settings; print(settings)"   # prints config, no secrets
```

Run `ngrok http 8000`, copy the host (no scheme) into `PUBLIC_HOSTNAME` in `.env`.

# PGAI Voice Tester

An automated voice bot that calls the Pretty Good AI test agent, acts as a realistic
patient across a range of scenarios, records and transcribes both sides of each call,
and is used to find bugs in the agent. Built with Twilio (telephony) + OpenAI's Realtime
API (speech-to-speech).

See `BUGS.md` for the findings and `ARCHITECTURE.md` for how it works and why.

## What it does

1. Places an outbound call from a Twilio number to the PGAI test line.
2. Bridges the call audio to OpenAI's Realtime API, which plays a "patient" persona
   (e.g. someone booking an appointment, asking about insurance, requesting a refill).
3. After the call, downloads the dual-channel recording from Twilio, transcribes each
   side with Whisper, and saves a speaker-labeled, timestamped transcript.
4. Saved artifacts land in `calls/` as `call-NN-<scenario>.{mp3,txt}`.

## Setup

Requirements: Python 3.11+ and `ffmpeg` (used to split the dual-channel recording).

```bash
# 1. clone and enter
git clone <your-repo-url>
cd pgai-voice-tester

# 2. virtualenv + deps
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 3. ffmpeg (macOS)
brew install ffmpeg          # Linux: apt-get install ffmpeg

# 4. config — copy the example and fill in your values
cp .env.example .env
# then edit .env (see "Environment variables" below)
```

### Environment variables (`.env`)

| Variable | What it is |
|---|---|
| `TWILIO_ACCOUNT_SID` | Twilio account SID |
| `TWILIO_AUTH_TOKEN` | Twilio auth token |
| `TWILIO_FROM_NUMBER` | your Twilio voice-capable number (E.164, e.g. +16505551234) |
| `OPENAI_API_KEY` | OpenAI API key with Realtime access |
| `OPENAI_REALTIME_MODEL` | realtime model (default `gpt-realtime`) |
| `PUBLIC_HOSTNAME` | your public ngrok hostname (no scheme), e.g. `abc123.ngrok-free.dev` |
| `TARGET_NUMBER` | the PGAI test line, +18054398008 (allowlisted) |

`.env` is gitignored and must not be committed.

> Note: the dialer has a hardcoded allowlist and will refuse to call any number that
> isn't the PGAI test line.

## Running a call

The server and the dialer are two separate processes, so you need three terminals
(server, tunnel, dialer). In each, activate the venv and export the cert path first:

```bash
source .venv/bin/activate
export SSL_CERT_FILE=$(python -c "import certifi; print(certifi.where())")
```

**Terminal 1 — the audio server:**
```bash
uvicorn src.server:app --port 8000
```

**Terminal 2 — the public tunnel** (must match `PUBLIC_HOSTNAME` in `.env`):
```bash
ngrok http 8000
```

**Terminal 3 — place a call:**
```bash
python run.py --call --scenario weekend-trap
```

`--scenario` picks the patient persona (default: `newpatient-morning`). After the call
finishes, the recording + transcript are saved to `calls/` automatically and the
channel→speaker mapping is printed so you can confirm roles didn't invert.

List available scenarios:
```bash
python run.py --help
```

## Scenarios

The 15 patient personas live in `src/scenarios.py` — scheduling, rescheduling/canceling,
refills, insurance/location/provider questions, and edge cases (interruptions, vague
requests, emergencies, wrong DOB, transfer requests). Each has a goal and, usually, a
"trap" whose correct answer is known from the real practice data in
`data/practice_info.md`.

## Notes

- macOS + python.org Python needs `SSL_CERT_FILE` set to certifi's bundle (above), or
  TLS handshakes to OpenAI/Twilio fail. The app code already uses a certifi SSL context.
- The OpenAI Realtime session config follows the current GA schema (`session.type`,
  nested `audio.input`/`audio.output`, `voice` under `audio.output`).
- Cost: each call is roughly $0.30–0.50 in API + telephony. The full 12-call batch was
  well under $20.

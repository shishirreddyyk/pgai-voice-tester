# Architecture

The bot places an outbound call with Twilio and bridges the live call audio to OpenAI's
Realtime API, which runs the "patient" side of the conversation. Concretely:
`run.py` dials the PGAI line via the Twilio REST API; Twilio fetches TwiML from the local
FastAPI server (`src/server.py`) exposed through ngrok, which returns a
`<Connect><Stream>` that opens a bidirectional WebSocket back to the server; for each
call the bridge (`src/bridge.py`) opens a second WebSocket to OpenAI's Realtime API and
pumps audio both ways (Twilio µ-law in → OpenAI, OpenAI µ-law out → Twilio), handling
barge-in and teardown. The chosen scenario travels from the CLI to the server as a Twilio
`<Parameter>`, so the bridge knows which persona (`src/scenarios.py`) to load into the
session. After the call, `src/capture.py` polls Twilio for the dual-channel recording,
and `src/transcript.py` splits the two channels, transcribes each with Whisper, and
merges them into one speaker-labeled, timestamped transcript — roles are assigned by who
speaks first (the agent always greets first), not by a hardcoded channel guess.

The main design choice was using a single **speech-to-speech** model (OpenAI Realtime)
instead of stitching together speech-to-text → LLM → text-to-speech. The deciding factor
was latency: a chained pipeline adds a noticeable gap on every turn, and the challenge is
explicit that voice quality and natural turn-taking are evaluated first, so anything that
makes the conversation feel laggy or robotic undercuts everything downstream. A single
model also preserves tone and handles interruptions more naturally. I deliberately
avoided managed voice-agent platforms (which would hide the part I'm supposed to
demonstrate — building it) and heavier orchestration frameworks (over-engineering for a
12-call tester). Recording is done on Twilio's side as a dual-channel recording so each
speaker lands on a separate channel, which makes post-call transcription clean and
speaker attribution reliable — important because mislabeling who said what would corrupt
every bug in the report. Test calls are guarded by a hardcoded allowlist so the dialer
can only ever call the assessment line.

"""OpenAI Realtime API connection + session config for the voice harness.

We talk to the Realtime API over a raw `websockets` connection (not the openai
SDK) so we control the TLS context and can forward µ-law frames untouched.

Invariants honored here:
- g711_ulaw for BOTH input and output audio (no transcoding).
- Listen-first: we send `session.update` only. We NEVER send `response.create`
  on startup — PGAI's agent answers and greets first; server-VAD picks that up
  as input and our bot replies after.
- certifi SSL context on the outbound wss (python.org Python 3.14 otherwise
  fails CERTIFICATE_VERIFY_FAILED).
"""

from __future__ import annotations

import ssl

import certifi
import websockets

from .config import settings

# Explicit CA bundle — REQUIRED on python.org Python builds, which don't use the
# system keychain. Reused for every outbound TLS/wss connection in the harness.
SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())

REALTIME_URL = "wss://api.openai.com/v1/realtime?model={model}"

# ---------------------------------------------------------------------------
# The single hardcoded scenario for Phase 1: a patient booking a new
# appointment. Kept deliberately SHORT — long personas make the model monologue
# and wreck turn-taking. One goal, brief natural turns, listen-first, exit when
# done. (The scenario suite arrives in Phase 3.)
# ---------------------------------------------------------------------------
# Short slug for the active scenario, used in capture filenames
# (calls/call-NN-<scenario>.{mp3,txt}). The scenario suite arrives in Phase 3.
SCENARIO_NAME = "newpatient"

PATIENT_INSTRUCTIONS = """\
You are a patient calling a medical practice to book a new appointment. Your \
name is Jordan Avery. You want the earliest available appointment with a \
primary care provider for a routine check-up, and you prefer a morning slot.

How to behave on the call:
- LISTEN FIRST. The other side answers and greets you. Do not speak until they \
have greeted you, then respond naturally to what they actually said.
- Keep every turn SHORT and conversational — one or two sentences. Never give \
speeches or list everything at once. Let them ask you questions.
- React to what they say and ask normal follow-up questions (e.g. confirm the \
date and time, ask what to bring).
- If they ask for your details, give: name Jordan Avery, date of birth March 12 \
1990, callback number is the number you're calling from.
- You are a real human patient. Never reveal or hint that you are an AI.
- Once the appointment is booked (or it's clear it can't be), briefly confirm, \
thank them, and say goodbye to end the call. Don't trail off into silence.
"""


def session_update_payload() -> dict:
    """Build the `session.update` event sent right after connecting.

    Sets the patient persona, a natural voice, g711_ulaw both directions, and
    server-VAD turn detection. Deliberately omits `input_audio_transcription`
    (Phase 2) and never triggers a response (listen-first).
    """
    return {
        "type": "session.update",
        "session": {
            # GA Realtime requires session.type; audio config nests under
            # session.audio.{input,output}; µ-law is the object form audio/pcmu.
            "type": "realtime",
            "instructions": PATIENT_INSTRUCTIONS,
            "audio": {
                "input": {
                    "format": {"type": "audio/pcmu"},
                    "turn_detection": {
                        "type": "server_vad",
                        "threshold": 0.5,
                        "prefix_padding_ms": 300,
                        "silence_duration_ms": 600,
                    },
                },
                "output": {
                    "format": {"type": "audio/pcmu"},
                    "voice": "marin",
                },
            },
        },
    }


async def connect():
    """Open a Realtime websocket with auth + certifi SSL.

    `websockets` renamed the header kwarg across versions (`extra_headers` →
    `additional_headers`). Try the modern name first, fall back to the legacy one
    so this works regardless of the installed version.
    """
    url = REALTIME_URL.format(model=settings.openai_realtime_model)
    headers = {"Authorization": f"Bearer {settings.openai_api_key}"}
    try:
        return await websockets.connect(
            url, additional_headers=headers, ssl=SSL_CONTEXT, max_size=None
        )
    except TypeError:
        return await websockets.connect(
            url, extra_headers=headers, ssl=SSL_CONTEXT, max_size=None
        )

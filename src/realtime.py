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

def session_update_payload(instructions: str) -> dict:
    """Build the `session.update` event sent after the Twilio stream starts.

    `instructions` is the selected scenario's patient persona. Sets a natural
    voice, g711_ulaw both directions, and server-VAD turn detection. Deliberately
    omits `input_audio_transcription` (post-call Whisper handles transcripts) and
    never triggers a response (listen-first).
    """
    return {
        "type": "session.update",
        "session": {
            # GA Realtime requires session.type; audio config nests under
            # session.audio.{input,output}; µ-law is the object form audio/pcmu.
            "type": "realtime",
            "instructions": instructions,
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

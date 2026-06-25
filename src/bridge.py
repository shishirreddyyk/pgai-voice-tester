"""Audio bridge: Twilio Media Streams <-> OpenAI Realtime.

One `run_bridge` call drives one phone call. Two async tasks shuttle base64
µ-law frames in each direction; both formats are g711_ulaw so payloads pass
through untouched (no transcoding).

Invariants honored here:
- Listen-first: we send `session.update` only, never `response.create`.
- Barge-in: on the agent's `speech_started`, flush Twilio's queued bot audio
  with a `clear` event so the bot stops talking.
- Teardown + cap: both sockets are closed on every exit path; a hard ~4 min
  cap force-ends a stuck call by tearing the sockets down.
"""

from __future__ import annotations

import asyncio
import json
import logging

import websockets
from fastapi import WebSocket, WebSocketDisconnect

from . import realtime, scenarios

logger = logging.getLogger("bridge")

# Hard cap on call duration. A leaked/confused call burns money silently;
# closing the sockets ends the call because Twilio's <Connect> blocks on the ws.
MAX_CALL_SECONDS = 240


async def _read_start(twilio_ws: WebSocket) -> tuple[str | None, str]:
    """Read Twilio events until `start`; return (stream_sid, scenario_slug).

    The scenario is passed by the dialer as a <Stream> <Parameter>, which Twilio
    delivers in start.customParameters — this is how the CLI's --scenario choice
    reaches the (separate) server process.
    """
    while True:
        raw = await twilio_ws.receive_text()
        msg = json.loads(raw)
        event = msg.get("event")
        if event == "start":
            stream_sid = msg["start"]["streamSid"]
            params = msg["start"].get("customParameters") or {}
            slug = params.get("scenario", scenarios.DEFAULT_SCENARIO)
            logger.info("stream started: %s (scenario=%s)", stream_sid, slug)
            return stream_sid, slug
        if event == "stop":
            return None, scenarios.DEFAULT_SCENARIO


async def run_bridge(twilio_ws: WebSocket) -> None:
    """Bridge one Twilio media stream to one OpenAI Realtime session."""
    openai_ws = await realtime.connect()

    # Pre-roll: learn streamSid + scenario from Twilio's `start` BEFORE we
    # configure the OpenAI session, so we load the right patient persona.
    try:
        stream_sid, slug = await _read_start(twilio_ws)
    except (WebSocketDisconnect, websockets.ConnectionClosed):
        await openai_ws.close()
        return
    if stream_sid is None:  # stopped before it started
        await openai_ws.close()
        return

    state: dict[str, str | None] = {"stream_sid": stream_sid}
    scenario = scenarios.get_scenario(slug)

    # Configure the session with the scenario persona. NO response.create —
    # listen-first: the agent greets first and server-VAD picks that up.
    await openai_ws.send(
        json.dumps(realtime.session_update_payload(scenario.instructions))
    )

    async def twilio_to_openai() -> None:
        """Twilio frames -> OpenAI input buffer."""
        try:
            while True:
                raw = await twilio_ws.receive_text()
                msg = json.loads(raw)
                event = msg.get("event")
                if event == "media":
                    await openai_ws.send(
                        json.dumps(
                            {
                                "type": "input_audio_buffer.append",
                                "audio": msg["media"]["payload"],
                            }
                        )
                    )
                elif event == "stop":
                    logger.info("twilio stop event")
                    return
                # `connected` and anything else: ignore.
        except WebSocketDisconnect:
            logger.info("twilio websocket disconnected")
        except websockets.ConnectionClosed:
            logger.info("openai websocket closed while reading twilio")

    async def openai_to_twilio() -> None:
        """OpenAI output -> Twilio frames, plus barge-in handling."""
        try:
            async for raw in openai_ws:
                msg = json.loads(raw)
                etype = msg.get("type")
                # Audio output event name differs across API versions.
                if etype in ("response.audio.delta", "response.output_audio.delta"):
                    delta = msg.get("delta")
                    if delta and state["stream_sid"]:
                        await twilio_ws.send_text(
                            json.dumps(
                                {
                                    "event": "media",
                                    "streamSid": state["stream_sid"],
                                    "media": {"payload": delta},
                                }
                            )
                        )
                elif etype == "input_audio_buffer.speech_started":
                    # Agent started talking -> flush queued bot audio (barge-in).
                    if state["stream_sid"]:
                        await twilio_ws.send_text(
                            json.dumps(
                                {
                                    "event": "clear",
                                    "streamSid": state["stream_sid"],
                                }
                            )
                        )
                elif etype == "error":
                    logger.error("openai error event: %s", msg.get("error"))
        except websockets.ConnectionClosed:
            logger.info("openai websocket closed")
        except WebSocketDisconnect:
            logger.info("twilio websocket disconnected while sending")

    pump = asyncio.gather(twilio_to_openai(), openai_to_twilio())
    try:
        await asyncio.wait_for(pump, timeout=MAX_CALL_SECONDS)
    except asyncio.TimeoutError:
        logger.warning("max call duration (%ss) reached — ending call", MAX_CALL_SECONDS)
    except Exception:  # noqa: BLE001 — log and still tear down
        logger.exception("bridge error")
    finally:
        pump.cancel()
        # Tear down BOTH sockets on every path (hangup, timeout, error).
        try:
            await openai_ws.close()
        except Exception:  # noqa: BLE001
            pass
        try:
            await twilio_ws.close()
        except Exception:  # noqa: BLE001
            pass
        logger.info("bridge torn down")

"""FastAPI app: serves outbound TwiML and the media-stream websocket.

Twilio fetches `/twiml` when the outbound call connects, which tells it to open a
bidirectional Media Stream to `/media-stream`; that websocket is handed to the
audio bridge.
"""

from __future__ import annotations

import logging
from xml.sax.saxutils import quoteattr

from fastapi import FastAPI, Request, WebSocket
from fastapi.responses import PlainTextResponse

from . import scenarios
from .bridge import run_bridge
from .config import settings

logging.basicConfig(level=logging.INFO)

app = FastAPI()


@app.get("/health")
def health() -> dict:
    return {"ok": True}


@app.api_route("/twiml", methods=["GET", "POST"])
def twiml(request: Request) -> PlainTextResponse:
    """Outbound TwiML: open a bidirectional Media Stream to /media-stream.

    <Connect> is bidirectional and blocks the call until the websocket closes —
    which is how the bridge's duration cap / teardown ends the call. The chosen
    scenario rides along as a <Parameter> so the bridge can load its persona.
    """
    scenario = request.query_params.get("scenario", scenarios.DEFAULT_SCENARIO)
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<Response><Connect>"
        f'<Stream url="wss://{settings.public_hostname}/media-stream">'
        f"<Parameter name=\"scenario\" value={quoteattr(scenario)}/>"
        "</Stream>"
        "</Connect></Response>"
    )
    return PlainTextResponse(content=xml, media_type="text/xml")


@app.websocket("/media-stream")
async def media_stream(ws: WebSocket) -> None:
    await ws.accept()
    await run_bridge(ws)

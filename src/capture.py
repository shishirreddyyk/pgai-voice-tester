"""Post-call capture: pull the dual-channel recording from Twilio and save the
two per-call artifacts under calls/ (flat naming):

    calls/call-NN-<scenario>.mp3   (ground-truth recording)
    calls/call-NN-<scenario>.txt   (reference transcript)

This is the minimal, reliable capture for Phase 2 — recording + transcript only.
No latency log, no eval, no scenario suite.
"""

from __future__ import annotations

import base64
import logging
import time
import urllib.request
from pathlib import Path

from twilio.rest import Client

from . import transcript
from .config import settings
from .realtime import SSL_CONTEXT  # certifi-backed; needed for the mp3 download

logger = logging.getLogger("capture")

CALLS_DIR = Path("calls")
TERMINAL_CALL_STATUSES = {"completed", "busy", "failed", "no-answer", "canceled"}


def _next_index() -> int:
    """Next NN: one past the highest existing call-NN-*.mp3 in calls/."""
    CALLS_DIR.mkdir(exist_ok=True)
    nums = []
    for p in CALLS_DIR.glob("call-*-*.mp3"):
        try:
            nums.append(int(p.name.split("-")[1]))
        except (IndexError, ValueError):
            continue
    return max(nums) + 1 if nums else 1


def _wait_for_call_completion(client: Client, call_sid: str,
                              timeout: int = 360, poll: int = 3) -> str | None:
    waited = 0
    while waited < timeout:
        status = client.calls(call_sid).fetch().status
        if status in TERMINAL_CALL_STATUSES:
            logger.info("call %s completed with status=%s", call_sid, status)
            return status
        time.sleep(poll)
        waited += poll
    logger.warning("timed out waiting for call %s to complete", call_sid)
    return None


def _wait_for_recording(client: Client, call_sid: str,
                        timeout: int = 90, poll: int = 3):
    """Twilio needs a few seconds to process the recording — poll until ready."""
    waited = 0
    while waited < timeout:
        recs = client.recordings.list(call_sid=call_sid, limit=1)
        if recs and recs[0].status == "completed":
            return recs[0]
        time.sleep(poll)
        waited += poll
    logger.error("recording for call %s not ready after %ss", call_sid, timeout)
    return None


def _download_mp3(recording_sid: str, dest: Path) -> None:
    url = (
        f"https://api.twilio.com/2010-04-01/Accounts/"
        f"{settings.twilio_account_sid}/Recordings/{recording_sid}.mp3"
    )
    token = base64.b64encode(
        f"{settings.twilio_account_sid}:{settings.twilio_auth_token}".encode()
    ).decode()
    req = urllib.request.Request(url, headers={"Authorization": f"Basic {token}"})
    with urllib.request.urlopen(req, context=SSL_CONTEXT) as resp, open(dest, "wb") as f:
        f.write(resp.read())


def capture_call(call_sid: str, scenario: str) -> dict:
    """Wait for the call to finish, save the recording, then the transcript.

    Returns {mp3, txt, mapping} (txt/mapping omitted if transcription fails).
    The mp3 is always saved first — it's the ground truth — so a transcript
    failure never costs us the recording.
    """
    client = Client(settings.twilio_account_sid, settings.twilio_auth_token)
    _wait_for_call_completion(client, call_sid)

    rec = _wait_for_recording(client, call_sid)
    if rec is None:
        return {}

    idx = _next_index()
    base = CALLS_DIR / f"call-{idx:02d}-{scenario}"
    mp3_path = base.with_suffix(".mp3")
    _download_mp3(rec.sid, mp3_path)
    logger.info("saved recording: %s", mp3_path)

    result: dict = {"mp3": mp3_path}
    try:
        text, mapping = transcript.build_transcript(mp3_path)
        txt_path = base.with_suffix(".txt")
        txt_path.write_text(text + "\n")
        logger.info("saved transcript: %s", txt_path)
        result["txt"] = txt_path
        result["mapping"] = mapping
    except Exception:  # noqa: BLE001 — recording is safe; transcript is best-effort
        logger.exception("transcript failed (recording is saved at %s)", mp3_path)

    return result

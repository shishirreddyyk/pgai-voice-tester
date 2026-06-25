"""Build a speaker-labeled, timestamped transcript from a dual-channel recording.

Approach (post-call, on the saved mp3):
1. ffmpeg splits the stereo recording into two mono channels (left/right).
2. Each channel is transcribed separately by Whisper, so every line is already
   attributed to a physical channel — no diarization needed.
3. Roles are assigned by WHO SPEAKS FIRST. The listen-first invariant guarantees
   the PGAI agent greets first, so the channel with the earliest first segment is
   the AGENT and the other is our PATIENT bot. We do NOT rely on Twilio's L/R
   channel convention (which is easy to get inverted).

The recording is ground truth; this transcript is a reference, so we optimize for
reliable attribution over verbatim perfection.
"""

from __future__ import annotations

import logging
import subprocess
import tempfile
from pathlib import Path

from openai import OpenAI

from .config import settings

logger = logging.getLogger("transcript")

# Vocabulary hint for Whisper. The audio is an 8 kHz phone call with healthcare
# terms; biasing toward likely domain words improves accuracy on the call.
WHISPER_PROMPT = (
    "Phone call with a medical practice using athenahealth. Likely terms: "
    "appointment, schedule, reschedule, cancellation, primary care physician, "
    "referral, prescription refill, pharmacy, dosage, milligrams, copay, "
    "deductible, insurance, in-network, date of birth, lab results, "
    "ibuprofen, amoxicillin, lisinopril, blood pressure, annual physical."
)


def _seg_get(seg, key):
    """Segment may be a pydantic object or a dict depending on SDK version."""
    if isinstance(seg, dict):
        return seg.get(key)
    return getattr(seg, key, None)


def _mmss(seconds: float) -> str:
    s = int(seconds)
    return f"{s // 60:02d}:{s % 60:02d}"


def _split_channels(mp3_path: Path, tmpdir: str) -> tuple[Path, Path]:
    """Split a stereo mp3 into two mono WAVs (scratch — never saved to calls/)."""
    left = Path(tmpdir) / "left.wav"
    right = Path(tmpdir) / "right.wav"
    subprocess.run(
        [
            "ffmpeg", "-y", "-i", str(mp3_path),
            "-filter_complex",
            "[0:a]channelsplit=channel_layout=stereo[l][r]",
            "-map", "[l]", str(left),
            "-map", "[r]", str(right),
        ],
        check=True,
        capture_output=True,
    )
    return left, right


def _transcribe(client: OpenAI, wav_path: Path) -> list:
    """Whisper transcription with segment timestamps for one mono channel."""
    with open(wav_path, "rb") as f:
        resp = client.audio.transcriptions.create(
            model="whisper-1",
            file=f,
            response_format="verbose_json",
            prompt=WHISPER_PROMPT,
        )
    return list(getattr(resp, "segments", None) or [])


def _first_start(segs: list) -> float:
    starts = [
        float(_seg_get(s, "start"))
        for s in segs
        if _seg_get(s, "start") is not None
    ]
    return min(starts) if starts else float("inf")


def build_transcript(mp3_path: Path) -> tuple[str, dict]:
    """Return (transcript_text, mapping) for a dual-channel recording.

    mapping = {agent_channel, patient_channel, first_speech_s} — surfaced to the
    caller so the AGENT/PATIENT assignment can be confirmed by ear.
    """
    client = OpenAI(api_key=settings.openai_api_key)
    with tempfile.TemporaryDirectory() as tmp:
        left, right = _split_channels(mp3_path, tmp)
        left_segs = _transcribe(client, left)
        right_segs = _transcribe(client, right)

    left_first = _first_start(left_segs)
    right_first = _first_start(right_segs)

    # Earliest speaker is the AGENT (listen-first → the agent greets first).
    if left_first <= right_first:
        agent_ch, patient_ch = "left", "right"
        agent_segs, patient_segs = left_segs, right_segs
    else:
        agent_ch, patient_ch = "right", "left"
        agent_segs, patient_segs = right_segs, left_segs

    first_speech = min(left_first, right_first)
    mapping = {
        "agent_channel": agent_ch,
        "patient_channel": patient_ch,
        "first_speech_s": first_speech if first_speech != float("inf") else 0.0,
    }
    logger.info(
        "channel mapping: AGENT=%s, PATIENT=%s (first speech %.2fs)",
        agent_ch, patient_ch, mapping["first_speech_s"],
    )

    rows = (
        [(s, "AGENT") for s in agent_segs]
        + [(s, "PATIENT") for s in patient_segs]
    )
    rows.sort(key=lambda r: float(_seg_get(r[0], "start") or 0.0))

    lines = []
    for seg, role in rows:
        text = (_seg_get(seg, "text") or "").strip()
        if not text:
            continue
        start = float(_seg_get(seg, "start") or 0.0)
        lines.append(f"[{_mmss(start)}] {role}: {text}")

    return "\n".join(lines), mapping

"""Outbound dialer. The ONLY place that places a call.

Hard invariant: this harness may only ever dial the allowlisted test agent.
`place_call` raises before touching Twilio if the target isn't in
`ALLOWED_NUMBERS`. One caller ID (`TWILIO_FROM_NUMBER`) for every call.
"""

from __future__ import annotations

import logging

from twilio.rest import Client

from .config import ALLOWED_NUMBERS, settings

logger = logging.getLogger("caller")


def place_call() -> str:
    """Place one outbound call to the allowlisted target. Returns the call SID."""
    if settings.target_number not in ALLOWED_NUMBERS:
        raise RuntimeError(
            f"Refusing to dial {settings.target_number!r}: not in the hardcoded "
            f"allowlist {sorted(ALLOWED_NUMBERS)}."
        )

    client = Client(settings.twilio_account_sid, settings.twilio_auth_token)
    call = client.calls.create(
        to=settings.target_number,
        from_=settings.twilio_from_number,
        url=f"https://{settings.public_hostname}/twiml",
        method="POST",
        # Minimal Twilio-side recording so a playable, dual-channel recording
        # appears in the Twilio console. (Full capture pipeline is Phase 2.)
        record=True,
        recording_channels="dual",
    )
    logger.info("placed call %s -> %s", call.sid, settings.target_number)
    return call.sid

"""Typed environment config loader for the PGAI voice-eval harness.

Loads from `.env` (via python-dotenv) and the process environment, validates
that required values are present, and exposes a singleton `settings`.

Invariant: we only ever dial the test agent. `ALLOWED_NUMBERS` is the hardcoded
allowlist the dialer will check against in a later phase — the target number is
never read as free-form config that could be pointed elsewhere.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv
from pydantic import BaseModel, field_validator

# Hardcoded dial allowlist. The only number this harness may ever call.
ALLOWED_NUMBERS: frozenset[str] = frozenset({"+18054398008"})

load_dotenv()


class _MissingEnv(RuntimeError):
    """Raised when a required environment variable is absent or empty."""


def _require(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise _MissingEnv(
            f"Required environment variable {name!r} is missing or empty. "
            f"Copy .env.example to .env and fill it in."
        )
    return value


def _optional(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


class Settings(BaseModel):
    """Validated runtime configuration. Fails loudly on missing required env."""

    openai_api_key: str
    openai_realtime_model: str
    twilio_account_sid: str
    twilio_auth_token: str
    twilio_from_number: str
    public_hostname: str
    target_number: str

    @field_validator("target_number")
    @classmethod
    def _target_must_be_allowlisted(cls, v: str) -> str:
        if v not in ALLOWED_NUMBERS:
            raise ValueError(
                f"TARGET_NUMBER {v!r} is not in the hardcoded allowlist "
                f"{sorted(ALLOWED_NUMBERS)}. This harness only dials the test agent."
            )
        return v

    def __str__(self) -> str:  # never print secrets
        return (
            "Settings("
            f"openai_realtime_model={self.openai_realtime_model!r}, "
            f"twilio_from_number={self.twilio_from_number!r}, "
            f"public_hostname={self.public_hostname!r}, "
            f"target_number={self.target_number!r}, "
            "openai_api_key=***, twilio_account_sid=***, twilio_auth_token=***)"
        )


def load_settings() -> Settings:
    return Settings(
        openai_api_key=_require("OPENAI_API_KEY"),
        openai_realtime_model=_optional("OPENAI_REALTIME_MODEL", "gpt-realtime"),
        twilio_account_sid=_require("TWILIO_ACCOUNT_SID"),
        twilio_auth_token=_require("TWILIO_AUTH_TOKEN"),
        twilio_from_number=_require("TWILIO_FROM_NUMBER"),
        public_hostname=_require("PUBLIC_HOSTNAME"),
        target_number=_optional("TARGET_NUMBER", "+18054398008"),
    )


settings = load_settings()


if __name__ == "__main__":
    print(settings)

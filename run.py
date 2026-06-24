"""CLI entry point.

    python run.py --call

Places ONE outbound call to the allowlisted test agent. The FastAPI server and
ngrok tunnel must already be running so the media-stream endpoint is live before
the call connects:

    1. uvicorn src.server:app --port 8000     # terminal 1
    2. ngrok http 8000  -> put host in PUBLIC_HOSTNAME (.env)   # terminal 2
    3. python run.py --call                    # terminal 3
"""

from __future__ import annotations

import argparse


def main() -> None:
    parser = argparse.ArgumentParser(description="PGAI voice-eval harness")
    parser.add_argument(
        "--call",
        action="store_true",
        help="place one outbound call to the allowlisted test agent",
    )
    args = parser.parse_args()

    if not args.call:
        parser.print_help()
        return

    # Imported here so --help works without a fully populated .env.
    from src.caller import place_call

    sid = place_call()
    print(f"Call placed: {sid}")
    print("Make sure `uvicorn src.server:app --port 8000` and ngrok are running.")


if __name__ == "__main__":
    main()

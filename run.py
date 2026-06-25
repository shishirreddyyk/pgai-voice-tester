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
    parser.add_argument(
        "--scenario",
        default=None,
        help="scenario slug to run (default: baseline newpatient-morning)",
    )
    args = parser.parse_args()

    if not args.call:
        parser.print_help()
        return

    # Imported here so --help works without a fully populated .env.
    from src.caller import place_call
    from src.capture import capture_call
    from src.scenarios import DEFAULT_SCENARIO, get_scenario

    slug = args.scenario or DEFAULT_SCENARIO
    # Validate before dialing so a typo fails fast (lists valid slugs).
    try:
        scenario = get_scenario(slug)
    except KeyError as e:
        raise SystemExit(str(e).strip('"'))

    sid = place_call(slug)
    print(f"Call placed: {sid}  (scenario: {scenario.slug} — {scenario.title})")
    print("Make sure `uvicorn src.server:app --port 8000` and ngrok are running.")
    print("Waiting for the call to finish, then pulling recording + transcript...")

    result = capture_call(sid, slug)
    if not result:
        print("No recording was captured — check the Twilio console.")
        return

    print(f"\nRecording:  {result['mp3']}")
    if "mapping" in result:
        m = result["mapping"]
        print(f"Transcript: {result['txt']}")
        print(
            f"\nChannel mapping → AGENT={m['agent_channel']}, "
            f"PATIENT={m['patient_channel']} "
            f"(first speech at {m['first_speech_s']:.2f}s = the AGENT greeting)"
        )
        print("Confirm by ear that AGENT/PATIENT didn't invert.")
    else:
        print("Transcript step failed; the recording above is still saved.")


if __name__ == "__main__":
    main()

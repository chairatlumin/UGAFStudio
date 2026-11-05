"""Run the localhost-only, read-only Unreal QA telemetry receiver."""

from __future__ import annotations

import argparse
import os
import signal
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.database.database import QADatabase
from qa_framework.gameplay_agent.unreal_telemetry import (
    UnrealTelemetryAdapter,
    UnrealTelemetryHTTPServer,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", required=True, help="existing QA game profile key")
    parser.add_argument("--build-id", required=True, help="exact game build identifier")
    parser.add_argument("--session-id", required=True, help="unique QA run/session identifier")
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--database", type=Path, help="defaults to this profile's local database")
    args = parser.parse_args()

    token = os.environ.get("UGAF_UNREAL_BRIDGE_TOKEN", "")
    if len(token) < 24:
        parser.error("set UGAF_UNREAL_BRIDGE_TOKEN to a secret of at least 24 characters")
    db = QADatabase(args.database) if args.database else QADatabase.for_profile(args.profile)
    if not any(game["profile"] == args.profile for game in db.list_games()):
        parser.error(f"profile is not registered in the selected database: {args.profile}")

    adapter = UnrealTelemetryAdapter(args.profile, args.build_id)
    server = UnrealTelemetryHTTPServer(
        adapter,
        token,
        host="127.0.0.1",
        port=args.port,
        persist=lambda event: db.record_unreal_telemetry_event(
            args.profile, args.session_id, event
        ),
    )
    stopped = threading.Event()

    def stop(_signum: int, _frame: object) -> None:
        if not stopped.is_set():
            stopped.set()
            threading.Thread(target=server.shutdown, daemon=True).start()

    signal.signal(signal.SIGINT, stop)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, stop)
    print(
        f"UGAF Unreal telemetry ready at http://127.0.0.1:{server.address[1]} "
        f"(profile={args.profile}, build={args.build_id}, session={args.session_id}). "
        "Read-only routes: GET /health, GET /v1/state, POST /v1/events."
    )
    try:
        server.serve_forever()
    finally:
        server.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

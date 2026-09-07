"""A separate OS process that competes for a summarization lease.

Driven by ``test_summarization_lease_cross_process.py``. It exists as its own
file, run with its own interpreter, because the thing under test is exclusion
*between processes*: two coroutines in one event loop share the manager's dict
and would agree with each other no matter what the database did. A real second
process has its own dict, its own engine and its own connection pool, so the
only thing that can make it back off is the shared row.

Prints exactly one JSON object on stdout.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--session-id", required=True)
    parser.add_argument(
        "--op",
        default="acquire",
        choices=("acquire", "probe", "impostor-release"),
    )
    parser.add_argument(
        "--start-at",
        type=float,
        default=0.0,
        help="Unix time to begin the operation, so N children collide on purpose.",
    )
    parser.add_argument(
        "--hold-seconds",
        type=float,
        default=0.0,
        help="Stay alive holding the lease before exiting.",
    )
    parser.add_argument(
        "--release",
        action="store_true",
        help="Release before exiting. Without it, exiting leaves the lease behind, "
        "which is what a crashed backend looks like.",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()

    # Spin rather than sleep: the point is for every child to call acquire in
    # the same millisecond.
    while time.time() < args.start_at:
        time.sleep(0.0005)

    from services.summarization_lease import (  # noqa: PLC0415 — after the barrier
        _is_held_row,
        _release_row,
        holder_id,
        summarization_lease,
    )

    result = {"pid": os.getpid(), "holder": holder_id(), "op": args.op}

    if args.op == "probe":
        result["is_held"] = _is_held_row(args.session_id)
    elif args.op == "impostor-release":
        # A process that does not own the lease tries to clear it.
        _release_row(args.session_id, "impostor:definitely-not-the-owner")
        result["is_held"] = _is_held_row(args.session_id)
    else:

        async def _run() -> None:
            acquired = await summarization_lease.acquire(args.session_id)
            result["acquired"] = bool(acquired)
            # acquire() fails OPEN when the database is unreachable, so a
            # misconfigured test would see every child "win" and could read
            # that as success. Report it so the tests can refuse to pass.
            local = summarization_lease._leases.get(args.session_id)
            result["degraded"] = bool(local is not None and local.degraded)
            if acquired and args.hold_seconds:
                await asyncio.sleep(args.hold_seconds)
            if acquired and args.release:
                await summarization_lease.release(args.session_id)
                result["released"] = True

        asyncio.run(_run())

    print(json.dumps(result), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())

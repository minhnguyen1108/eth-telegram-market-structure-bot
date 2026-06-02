from __future__ import annotations

import sys

from src.jobs import run_daily_summary, run_signal_scan, run_trade_evaluation


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python -m src.main [scan|evaluate|daily-summary]")
        return 1

    command = sys.argv[1]
    if command == "scan":
        print(run_signal_scan())
        return 0
    if command == "evaluate":
        print(run_trade_evaluation())
        return 0
    if command == "daily-summary":
        print(run_daily_summary())
        return 0

    print(f"Unknown command: {command}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

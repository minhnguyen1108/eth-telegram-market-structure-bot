from __future__ import annotations

import sys
import unittest
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.jobs import is_weekend_trade


class TradeWindowFiltersTest(unittest.TestCase):
    def test_skips_saturday_trade_time(self) -> None:
        self.assertTrue(is_weekend_trade(datetime(2026, 6, 27, 9, 0)))

    def test_allows_friday_trade_time(self) -> None:
        self.assertFalse(is_weekend_trade(datetime(2026, 6, 26, 9, 0)))


if __name__ == "__main__":
    unittest.main()

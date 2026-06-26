from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.bitget_client import BitgetClient


class FakeResponse:
    def __init__(self, status_code: int, payload: dict) -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = str(payload)

    def json(self) -> dict:
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} Client Error", response=self)


class BitgetClientTest(unittest.TestCase):
    def test_http_error_includes_bitget_response_body(self) -> None:
        client = BitgetClient(api_key="key", api_secret="secret", passphrase="pass")

        with patch(
            "src.bitget_client.requests.post",
            return_value=FakeResponse(
                400,
                {
                    "code": "40762",
                    "msg": "The order size is greater than the max open size",
                },
            ),
        ):
            with self.assertRaisesRegex(RuntimeError, "40762.*max open size"):
                client.place_market_order(
                    symbol="ETHUSDT",
                    side="LONG",
                    size="0.01",
                    product_type="USDT-FUTURES",
                    margin_mode="isolated",
                    margin_coin="USDT",
                    take_profit=3400,
                    stop_loss=3300,
                    client_oid_prefix="test",
                )


if __name__ == "__main__":
    unittest.main()

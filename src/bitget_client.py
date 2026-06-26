from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from uuid import uuid4

import requests


@dataclass(frozen=True)
class BitgetOrderResult:
    order_id: str | None
    client_oid: str
    raw_response: dict


class BitgetClient:
    def __init__(
        self,
        *,
        api_key: str,
        api_secret: str,
        passphrase: str,
        base_url: str = "https://api.bitget.com",
    ) -> None:
        self.api_key = api_key
        self.api_secret = api_secret
        self.passphrase = passphrase
        self.base_url = base_url.rstrip("/")

    def _sign(self, timestamp: str, method: str, request_path: str, body: str = "") -> str:
        payload = f"{timestamp}{method.upper()}{request_path}{body}"
        digest = hmac.new(self.api_secret.encode(), payload.encode(), hashlib.sha256).digest()
        return base64.b64encode(digest).decode()

    def _post(self, request_path: str, payload: dict) -> dict:
        body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
        timestamp = str(int(time.time() * 1000))
        headers = {
            "ACCESS-KEY": self.api_key,
            "ACCESS-SIGN": self._sign(timestamp, "POST", request_path, body),
            "ACCESS-TIMESTAMP": timestamp,
            "ACCESS-PASSPHRASE": self.passphrase,
            "Content-Type": "application/json",
            "locale": "en-US",
        }
        response = requests.post(
            f"{self.base_url}{request_path}",
            headers=headers,
            data=body.encode("utf-8"),
            timeout=30,
        )
        try:
            data = response.json()
        except ValueError:
            data = {}
        if response.status_code >= 400:
            code = data.get("code", response.status_code)
            message = data.get("msg") or response.text
            raise RuntimeError(f"Bitget HTTP {response.status_code} error {code}: {message}")
        if data.get("code") != "00000":
            raise RuntimeError(f"Bitget API error {data.get('code')}: {data.get('msg')}")
        return data

    def place_market_order(
        self,
        *,
        symbol: str,
        side: str,
        size: str,
        product_type: str,
        margin_mode: str,
        margin_coin: str,
        take_profit: float,
        stop_loss: float,
        client_oid_prefix: str,
    ) -> BitgetOrderResult:
        client_oid = f"{client_oid_prefix}-{uuid4().hex[:12]}"
        payload = {
            "symbol": symbol,
            "productType": product_type,
            "marginMode": margin_mode,
            "marginCoin": margin_coin,
            "size": size,
            "side": "buy" if side == "LONG" else "sell",
            "tradeSide": "open",
            "orderType": "market",
            "clientOid": client_oid,
            "presetStopSurplusPrice": f"{take_profit:.8f}",
            "presetStopLossPrice": f"{stop_loss:.8f}",
        }
        data = self._post("/api/v2/mix/order/place-order", payload)
        order_data = data.get("data") or {}
        return BitgetOrderResult(
            order_id=order_data.get("orderId"),
            client_oid=order_data.get("clientOid") or client_oid,
            raw_response=data,
        )

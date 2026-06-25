from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    app_name: str = os.getenv("APP_NAME", "eth-telegram-bot")
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./trade_bot.db")
    telegram_bot_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    telegram_chat_id: str = os.getenv("TELEGRAM_CHAT_ID", "")
    symbol: str = os.getenv("SYMBOL", "ETHUSDT")
    symbols_csv: str = os.getenv("SYMBOLS", os.getenv("SYMBOL", "ETHUSDT"))
    bitget_api_key: str = os.getenv("BITGET_API_KEY", "")
    bitget_api_secret: str = os.getenv("BITGET_API_SECRET", "")
    bitget_api_passphrase: str = os.getenv("BITGET_API_PASSPHRASE", "")
    bitget_trading_enabled: bool = os.getenv("BITGET_TRADING_ENABLED", "false").lower() == "true"
    bitget_base_url: str = os.getenv("BITGET_BASE_URL", "https://api.bitget.com")
    bitget_product_type: str = os.getenv("BITGET_PRODUCT_TYPE", "USDT-FUTURES")
    bitget_margin_mode: str = os.getenv("BITGET_MARGIN_MODE", "isolated")
    bitget_margin_coin: str = os.getenv("BITGET_MARGIN_COIN", "USDT")
    bitget_default_order_size: str = os.getenv("BITGET_DEFAULT_ORDER_SIZE", "")
    bitget_symbol_map_csv: str = os.getenv("BITGET_SYMBOL_MAP", "XAUUSDT:XAUUSDT")
    timeframe: str = os.getenv("TIMEFRAME", "15m")
    higher_timeframe: str = os.getenv("HIGHER_TIMEFRAME", "4h")
    risk_reward: float = float(os.getenv("RISK_REWARD", "2.0"))
    min_signal_score: int = int(os.getenv("MIN_SIGNAL_SCORE", "3"))
    swing_enabled: bool = os.getenv("SWING_ENABLED", "true").lower() == "true"
    swing_timeframe: str = os.getenv("SWING_TIMEFRAME", "4h")
    swing_higher_timeframe: str = os.getenv("SWING_HIGHER_TIMEFRAME", "1d")
    swing_risk_reward: float = float(os.getenv("SWING_RISK_REWARD", "3.0"))
    swing_min_signal_score: int = int(os.getenv("SWING_MIN_SIGNAL_SCORE", "3"))
    max_open_trades_per_timeframe: int = int(os.getenv("MAX_OPEN_TRADES_PER_TIMEFRAME", "5"))
    winrate_alert_threshold: float = float(os.getenv("WINRATE_ALERT_THRESHOLD", "45"))
    timezone: str = os.getenv("TIMEZONE", "Asia/Bangkok")
    send_scan_status_when_no_signal: bool = os.getenv("SEND_SCAN_STATUS_WHEN_NO_SIGNAL", "false").lower() == "true"

    @property
    def symbols(self) -> tuple[str, ...]:
        symbols = tuple(symbol.strip().upper() for symbol in self.symbols_csv.split(",") if symbol.strip())
        return symbols or (self.symbol.upper(),)

    @property
    def bitget_symbol_map(self) -> dict[str, str]:
        mapping: dict[str, str] = {}
        for item in self.bitget_symbol_map_csv.split(","):
            if ":" not in item:
                continue
            source, target = item.split(":", 1)
            mapping[source.strip().upper()] = target.strip().upper()
        return mapping

    def bitget_symbol(self, symbol: str) -> str:
        return self.bitget_symbol_map.get(symbol.upper(), symbol.upper())

    def bitget_order_size(self, symbol: str) -> str:
        symbol_size = os.getenv(f"BITGET_ORDER_SIZE_{symbol.upper()}", "")
        return symbol_size or self.bitget_default_order_size


settings = Settings()

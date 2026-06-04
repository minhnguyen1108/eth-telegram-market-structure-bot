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


settings = Settings()

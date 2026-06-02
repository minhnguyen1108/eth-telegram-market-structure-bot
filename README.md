# ETH/USDT Market Structure Bot

This project scans `ETH/USDT` using a market structure + price action approach, sends alerts to Telegram, stores trade history in a database, and tracks win rate automatically.

## Strategy

The bot uses two timeframes:

- `4h`: determines the higher-timeframe bias using market structure and EMA50.
- `15m`: looks for break of structure, pullback into value, and price action confirmation.

A valid setup requires:

1. Higher-timeframe bias is aligned.
2. A break of structure appears on `15m`.
3. Price pulls back into the `0.382` to `0.618` zone of the latest impulse.
4. A confirmation candle appears as an `engulfing` candle or `pin bar`.
5. The internal setup score is above the configured threshold.

## Automated Jobs

The bot uses three jobs:

1. Signal scan every 15 minutes.
   The bot now sends a Telegram message even when there is no valid setup, if `SEND_SCAN_STATUS_WHEN_NO_SIGNAL=true`.
2. Trade evaluation on a 15-minute cycle offset from the scan.
   This checks whether open trades hit `TP` or `SL`, updates rolling win rate, and stores improvement recommendations when performance is weak.
3. Daily summary at `00:05` Asia/Bangkok time.
   This summarizes the previous trading day.

## Commands

Install dependencies:

```bash
pip install -r requirements.txt
```

Run signal scan:

```bash
python -m src.main scan
```

Run trade evaluation:

```bash
python -m src.main evaluate
```

Run daily summary:

```bash
python -m src.main daily-summary
```

## Deployment

As of June 3, 2026, the live setup is:

- GitHub Actions for execution
- External scheduler (`cron-job.org`) for reliable triggering
- Neon Postgres for storage

Why this setup:

- Some new repositories do not trigger GitHub `schedule` reliably enough for a time-sensitive bot.
- External schedulers are more predictable for fixed execution times.
- GitHub Actions still provides a simple and free execution layer for public repositories.
- The bot uses Binance public market data through `data-api.binance.vision`, which is more suitable for public market-data access from U.S.-hosted runners.

## Environment Variables

Required secrets:

- `DATABASE_URL`
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

Optional settings:

- `SYMBOL`
- `TIMEFRAME`
- `HIGHER_TIMEFRAME`
- `RISK_REWARD`
- `MIN_SIGNAL_SCORE`
- `WINRATE_ALERT_THRESHOLD`
- `TIMEZONE`
- `SEND_SCAN_STATUS_WHEN_NO_SIGNAL`

## Scheduler Notes

GitHub workflow files are configured for `workflow_dispatch` only.

The external scheduler is responsible for calling:

- `Scan Signals`
- `Evaluate Trades`
- `Daily Summary`

This avoids duplicate runs and makes the execution schedule easier to control.

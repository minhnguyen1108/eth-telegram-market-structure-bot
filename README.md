# ETH/USDT Market Structure Bot

Bot quet ETH/USDT theo market structure + price action, gui tin hieu ve Telegram, luu lich su lenh vao database va cap nhat winrate tu dong.

## Chien luoc

Bot dung 2 khung:

- `4h`: xac dinh bias chinh theo market structure va EMA50.
- `15m`: tim breakout of structure, cho gia hoi ve value zone va xac nhan bang nen price action.

Mot tin hieu hop le can:

1. Bias `4h` dong thuan.
2. Co break of structure tren `15m`.
3. Gia hoi ve vung `0.382` den `0.618` cua impulse gan nhat.
4. Co nen xac nhan dang `engulfing` hoac `pin bar`.
5. Diem chat luong du lon theo thang diem noi bo.

## 3 lich tu dong

1. Moi 15 phut quet tin hieu va gui Telegram neu co lenh.
2. Dinh ky cap nhat ket qua cac lenh dang mo, tinh winrate va tao goi y cai thien khi winrate thap.
3. Moi ngay tong hop winrate trong ngay va gui bao cao.
   Job nay nen chay sau 00:00 theo gio cua ban. Cau hinh hien tai dung `17:05 UTC`, tuong ung `00:05` gio `Asia/Bangkok`, de tong hop ngay vua ket thuc.

## Chay local

1. Tao file `.env` tu `.env.example`.
2. Cai goi:

```bash
pip install -r requirements.txt
```

3. Quet tin hieu:

```bash
python -m src.main scan
```

4. Cap nhat lenh:

```bash
python -m src.main evaluate
```

5. Bao cao ngay:

```bash
python -m src.main daily-summary
```

## Deploy free

As of June 2, 2026, giai phap free phu hop nhat cho bai toan nay la:

- GitHub Actions de chay 3 lich cron.
- Neon Postgres de luu database.

Ly do:

- GitHub Actions ho tro `schedule` voi cron va chu ky ngan nhat la 5 phut theo docs: [Workflow syntax for GitHub Actions](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax).
- GitHub-hosted runners mien phi cho public repository theo docs: [Billing and usage](https://docs.github.com/actions/learn-github-actions/usage-limits-billing-and-administration).
- Nhiều host web free hien nay se sleep khi khong co traffic, khong phu hop de giu scheduler trong app.
- Bot dang dung endpoint market data public `data-api.binance.vision`, phu hop hon cho moi truong runner dat tai My theo tai lieu chinh thuc cua Binance ve market-data-only URLs.

## GitHub Secrets can them

- `DATABASE_URL`
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

Neu muon doi threshold va tham so:

- `SYMBOL`
- `TIMEFRAME`
- `HIGHER_TIMEFRAME`
- `RISK_REWARD`
- `MIN_SIGNAL_SCORE`
- `WINRATE_ALERT_THRESHOLD`
- `TIMEZONE`

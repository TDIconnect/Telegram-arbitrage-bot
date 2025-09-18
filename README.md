# Telegram Arbitrage Bot (Binance, Bybit, KuCoin)

This is an **asynchronous Python bot** that scans for **cross-exchange arbitrage** opportunities on **USDT pairs** across **Binance**, **Bybit**, and **KuCoin**, and alerts/executes via **Telegram**.

> ⚠️ **Risk Warning**: Live trading is risky. Slippage, fees, rate limits, latency, partial fills, and API bans can cause losses. **Default mode is PAPER**. Switch to live only if you understand the risks.

---

## Features
- Monitors configurable symbols (default: BTC/USDT, ETH/USDT, SOL/USDT, XRP/USDT, DOGE/USDT)
- Scans **Binance**, **Bybit**, **KuCoin** via **ccxt.async_support**
- Calculates **net spread** including per-exchange taker fees and a slippage allowance
- **Paper trading** (default) with notional sizing
- **Live trading** (opt-in): simultaneous market buy on cheaper exchange & sell on richer exchange, sized by balances
- Telegram commands:
  - `/start`, `/help`
  - `/status` – show config, running state
  - `/symbols` – list or update symbols
  - `/setspread <bps>` – set minimum spread in basis points (1% = 100 bps)
  - `/paper` / `/live` – toggle trading mode
  - `/run` / `/stop` – start/stop scanning
- Clean shutdown & error handling

---

## Quick Start

1. **Create a Telegram bot** with BotFather and copy the **bot token**.

2. **Create API keys** (read/trade) on each exchange you plan to use:
   - Binance, Bybit, KuCoin
   - For **paper mode**, keys are optional (only needed if you want authenticated balances).

3. **Local Setup**

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, and exchange keys.
```

4. **Run the bot**

```bash
python bot.py
```

5. **In Telegram**
   - Send `/start`
   - Use `/run` to begin scanning, `/stop` to stop.
   - Default mode: **paper**. Switch to live with `/live`.

---

## Environment Variables

See `.env.example`. The most important are:

- `TELEGRAM_BOT_TOKEN` – token from BotFather
- `TELEGRAM_CHAT_ID` – your personal chat ID to restrict access (optional; if set, only that chat can use commands)
- `MODE` – `paper` (default) or `live`
- `SYMBOLS` – comma-separated list of symbols (e.g., `BTC/USDT,ETH/USDT`)
- `MIN_SPREAD_BPS` – min net spread (basis points) to act, default 20 (0.20%)
- `POLL_SECONDS` – scan interval, default 2s
- `SLIPPAGE_BPS` – slippage allowance (per leg), default 5 (0.05%)
- `PAPER_NOTIONAL_USD` – notional per trade in paper mode, default 200
- Exchange credentials: `BINANCE_KEY`, `BINANCE_SECRET`, etc.

---

## How It Works

For each symbol and scan cycle:
1. Fetch best bid/ask from each exchange (REST ticker or orderbook top).
2. For each pair of exchanges (A,B):
   - Compute buy on cheaper exchange (ask_A) vs sell on richer exchange (bid_B).
   - Apply taker fees and slippage on both legs.
   - If **net spread >= MIN_SPREAD_BPS**, generate a signal.
3. In **live mode**, place simultaneous market orders sized by balances and risk caps.
4. Report results to Telegram.

---

## Notes & Limitations

- REST polling is ~2–3s; WebSockets are faster.
- Fees/slippage are approximations; refine with exchange-specific fee tiers.
- Live trading requires free balances on **both** exchanges (no transfers).
- Minimal symbol normalization is handled by CCXT unified symbols; check mapping if a symbol is missing.
- This is a starter; extend with:
  - WebSocket prices, smart order sizing, partial-fill handling
  - Persistence (DB), PnL accounting
  - Per-exchange fee tiers & VIP levels
  - Risk limits per-symbol/exchange

---

## License
MIT

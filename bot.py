import os
import asyncio
from dotenv import load_dotenv
from typing import Dict, List, Any
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

from utils import env_str, env_float, env_int, fmt_usd
from exchanges import build_exchanges, load_markets_all, close_all
from arbitrage import ArbitrageScanner, ArbitrageExecutor

load_dotenv()

# --- Config (env) ---
TELEGRAM_BOT_TOKEN = env_str("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID   = env_str("TELEGRAM_CHAT_ID")
MODE               = env_str("MODE", "paper").lower()
SYMBOLS            = [s.strip() for s in env_str("SYMBOLS", "BTC/USDT,ETH/USDT,SOL/USDT,XRP/USDT,DOGE/USDT").split(",") if s.strip()]
MIN_SPREAD_BPS     = env_float("MIN_SPREAD_BPS", 20.0)
POLL_SECONDS       = env_float("POLL_SECONDS", 2.0)
SLIPPAGE_BPS       = env_float("SLIPPAGE_BPS", 5.0)
PAPER_NOTIONAL_USD = env_float("PAPER_NOTIONAL_USD", 200.0)

CREDS = {
    "binance": {"key": env_str("BINANCE_KEY"), "secret": env_str("BINANCE_SECRET")} if env_str("BINANCE_KEY") else None,
    "bybit":   {"key": env_str("BYBIT_KEY"), "secret": env_str("BYBIT_SECRET")} if env_str("BYBIT_KEY") else None,
    "kucoin":  {"key": env_str("KUCOIN_KEY"), "secret": env_str("KUCOIN_SECRET"), "passphrase": env_str("KUCOIN_PASSPHRASE")} if env_str("KUCOIN_KEY") else None,
}

STATE = {
    "mode": MODE,  # 'paper' or 'live'
    "symbols": SYMBOLS,
    "min_spread_bps": MIN_SPREAD_BPS,
    "poll_seconds": POLL_SECONDS,
    "slippage_bps": SLIPPAGE_BPS,
    "paper_notional_usd": PAPER_NOTIONAL_USD,
    "running": False,
    "task": None,
    "scanner": None,
    "executor": None,
    "exchanges": {},
}

def chat_allowed(update: Update) -> bool:
    if not TELEGRAM_CHAT_ID:
        return True
    chat_id = str(update.effective_chat.id) if update.effective_chat else ""
    user_id = str(update.effective_user.id) if update.effective_user else ""
    return (chat_id == TELEGRAM_CHAT_ID) or (user_id == TELEGRAM_CHAT_ID)

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not chat_allowed(update):
        return
    await update.message.reply_text(
        "🤖 *Arbitrage Bot Ready*\n"
        "Use /run to start scanning and /stop to stop.\n"
        "Mode: *%s*\n"
        "Symbols: %s\n"
        "Min spread: %s bps\n"
        "Slippage: %s bps\n"
        "Poll: %ss\n" % (
            STATE["mode"],
            ", ".join(STATE["symbols"]),
            STATE["min_spread_bps"],
            STATE["slippage_bps"],
            STATE["poll_seconds"],
        ),
        parse_mode=ParseMode.MARKDOWN
    )

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not chat_allowed(update): return
    await update.message.reply_text(
        "/start, /help, /status\n"
        "/symbols [list|add|remove] [SYMBOL]\n"
        "/setspread <bps>\n"
        "/paper  or  /live\n"
        "/run  or  /stop\n"
    )

async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not chat_allowed(update): return
    await update.message.reply_text(
        f"Running: {STATE['running']}\n"
        f"Mode: {STATE['mode']}\n"
        f"Symbols: {', '.join(STATE['symbols'])}\n"
        f"Min spread: {STATE['min_spread_bps']} bps\n"
        f"Slippage: {STATE['slippage_bps']} bps\n"
        f"Poll: {STATE['poll_seconds']}s\n"
        f"Paper notional: {fmt_usd(STATE['paper_notional_usd'])}\n"
    )

async def symbols_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not chat_allowed(update): return
    args = context.args or []
    if not args:
        await update.message.reply_text("Symbols: " + ", ".join(STATE["symbols"]))
        return
    action = args[0].lower()
    if action == "list":
        await update.message.reply_text("Symbols: " + ", ".join(STATE["symbols"]))
    elif action == "add" and len(args) > 1:
        sym = args[1].upper()
        if sym not in STATE["symbols"]:
            STATE["symbols"].append(sym)
        await update.message.reply_text("Added. Symbols: " + ", ".join(STATE["symbols"]))
    elif action == "remove" and len(args) > 1:
        sym = args[1].upper()
        if sym in STATE["symbols"]:
            STATE["symbols"].remove(sym)
        await update.message.reply_text("Removed. Symbols: " + ", ".join(STATE["symbols"]))
    else:
        await update.message.reply_text("Usage: /symbols [list|add|remove] [SYMBOL]")

async def setspread_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not chat_allowed(update): return
    args = context.args or []
    if not args:
        await update.message.reply_text("Current MIN_SPREAD_BPS = %s" % STATE["min_spread_bps"])
        return
    try:
        bps = float(args[0])
        STATE["min_spread_bps"] = bps
        await update.message.reply_text("OK. MIN_SPREAD_BPS = %s" % bps)
    except Exception:
        await update.message.reply_text("Usage: /setspread <bps>")

async def paper_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not chat_allowed(update): return
    STATE["mode"] = "paper"
    await update.message.reply_text("Mode switched to PAPER.")

async def live_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not chat_allowed(update): return
    STATE["mode"] = "live"
    await update.message.reply_text("Mode switched to LIVE. ⚠️ Live trading will place real orders.")

async def run_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not chat_allowed(update): return
    if STATE["running"]:
        await update.message.reply_text("Already running.")
        return

    # Build exchanges & scanner
    STATE["exchanges"] = build_exchanges({
        k: v for k, v in {
            "binance": CREDS.get("binance"),
            "bybit": CREDS.get("bybit"),
            "kucoin": CREDS.get("kucoin"),
        }.items() if v
    })
    if not STATE["exchanges"]:
        await update.message.reply_text("No exchanges configured. Add API keys in .env (or run paper mode without balances).")
    await load_markets_all(STATE["exchanges"])

    STATE["scanner"] = ArbitrageScanner(
        STATE["exchanges"], STATE["symbols"], STATE["min_spread_bps"], STATE["slippage_bps"]
    )
    STATE["executor"] = ArbitrageExecutor(
        STATE["exchanges"], STATE["mode"], STATE["paper_notional_usd"]
    )
    STATE["running"] = True
    STATE["task"] = asyncio.create_task(loop_scan(context))

    await update.message.reply_text("Started scanning.")

async def stop_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not chat_allowed(update): return
    STATE["running"] = False
    task = STATE.get("task")
    if task:
        task.cancel()
        try:
            await task
        except Exception:
            pass
        STATE["task"] = None
    await close_all(STATE["exchanges"])
    STATE["exchanges"].clear()
    await update.message.reply_text("Stopped.")

async def loop_scan(context: ContextTypes.DEFAULT_TYPE):
    chat_id = context._chat_id  # internal access; alternative: store from /start
    # If not available, fall back to env TELEGRAM_CHAT_ID
    if not chat_id:
        cid = os.getenv("TELEGRAM_CHAT_ID")
        chat_id = int(cid) if cid else None

    while STATE["running"]:
        try:
            signals = await STATE["scanner"].scan_once()
            if signals:
                for s in signals:
                    msg = (f"💡 *Arb Signal* {s['symbol']}\n"
                           f"Buy {s['buy_on']} @ {s['buy_px']:.6f}\n"
                           f"Sell {s['sell_on']} @ {s['sell_px']:.6f}\n"
                           f"Net: {s['net_spread_bps']:.2f} bps")
                    if chat_id:
                        await context.bot.send_message(chat_id=chat_id, text=msg, parse_mode=ParseMode.MARKDOWN)
                    res = await STATE["executor"].execute(s)
                    if chat_id:
                        await context.bot.send_message(chat_id=chat_id, text=f"Executed: {res}")
            await asyncio.sleep(STATE["poll_seconds"])
        except asyncio.CancelledError:
            break
        except Exception as e:
            if chat_id:
                await context.bot.send_message(chat_id=chat_id, text=f"Error in loop: {e}")
            await asyncio.sleep(STATE["poll_seconds"])

def main():
    if not TELEGRAM_BOT_TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN missing in env")
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("status", status_cmd))
    app.add_handler(CommandHandler("symbols", symbols_cmd))
    app.add_handler(CommandHandler("setspread", setspread_cmd))
    app.add_handler(CommandHandler("paper", paper_cmd))
    app.add_handler(CommandHandler("live", live_cmd))
    app.add_handler(CommandHandler("run", run_cmd))
    app.add_handler(CommandHandler("stop", stop_cmd))
    app.run_polling()

if __name__ == "__main__":
    main()

import ccxt.async_support as ccxt
from typing import Dict, Any

# Default taker fees (approx; override with your account tiers if needed)
DEFAULT_TAKER_FEES = {
    "binance": 0.001,   # 0.10%
    "bybit":   0.001,   # 0.10%
    "kucoin":  0.001,   # 0.10%
}

def build_exchanges(creds: dict) -> Dict[str, Any]:
    exs = {}
    if creds.get("binance"):
        exs["binance"] = ccxt.binance({
            "apiKey": creds["binance"]["key"],
            "secret": creds["binance"]["secret"],
            "enableRateLimit": True,
            "options": {"defaultType": "spot"},
        })
    if creds.get("bybit"):
        exs["bybit"] = ccxt.bybit({
            "apiKey": creds["bybit"]["key"],
            "secret": creds["bybit"]["secret"],
            "enableRateLimit": True,
            "options": {"defaultType": "spot"},
        })
    if creds.get("kucoin"):
        exs["kucoin"] = ccxt.kucoin({
            "apiKey": creds["kucoin"]["key"],
            "secret": creds["kucoin"]["secret"],
            "password": creds["kucoin"]["passphrase"],
            "enableRateLimit": True,
        })
    return exs

async def load_markets_all(exs: Dict[str, Any]) -> None:
    for ex in exs.values():
        await ex.load_markets()

async def close_all(exs: Dict[str, Any]) -> None:
    for ex in exs.values():
        try:
            await ex.close()
        except Exception:
            pass

def taker_fee(exchange_id: str) -> float:
    return DEFAULT_TAKER_FEES.get(exchange_id, 0.001)

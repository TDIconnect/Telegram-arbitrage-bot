import os
import math
from dataclasses import dataclass
from typing import Dict, Tuple

def env_str(key: str, default: str = "") -> str:
    v = os.getenv(key)
    return v if v is not None and v != "" else default

def env_float(key: str, default: float) -> float:
    v = os.getenv(key)
    try:
        return float(v) if v is not None and v != "" else default
    except Exception:
        return default

def env_int(key: str, default: int) -> int:
    v = os.getenv(key)
    try:
        return int(v) if v is not None and v != "" else default
    except Exception:
        return default

def bps_to_ratio(bps: float) -> float:
    return bps / 10_000.0

@dataclass
class PricePoint:
    bid: float
    ask: float

def effective_spread_bps(buy_price: float, sell_price: float, taker_fee_buy: float, taker_fee_sell: float, slippage_bps: float) -> float:
    # Apply slippage as bps on each leg
    buy_slip = buy_price * (1 + bps_to_ratio(slippage_bps))
    sell_slip = sell_price * (1 - bps_to_ratio(slippage_bps))
    # Apply taker fees as multipliers
    eff_buy = buy_slip * (1 + taker_fee_buy)
    eff_sell = sell_slip * (1 - taker_fee_sell)
    # Net spread ratio:
    if eff_buy <= 0:
        return -1e9
    spread_ratio = (eff_sell - eff_buy) / eff_buy
    return spread_ratio * 10_000.0  # to bps

def fmt_usd(x: float) -> str:
    return f"${x:,.2f}"

def safe_size_from_notional(notional_usd: float, price: float, min_qty: float = 0.0, step: float = 0.0) -> float:
    if price <= 0:
        return 0.0
    qty = notional_usd / price
    # round down to step
    if step and step > 0:
        qty = math.floor(qty / step) * step
    # enforce min
    if min_qty and qty < min_qty:
        return 0.0
    return qty

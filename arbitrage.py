import asyncio
from typing import Dict, List, Tuple, Any
from utils import PricePoint, effective_spread_bps, bps_to_ratio, safe_size_from_notional
from exchanges import taker_fee

class ArbitrageScanner:
    def __init__(self, exs: Dict[str, Any], symbols: List[str], min_spread_bps: float, slippage_bps: float):
        self.exs = exs
        self.symbols = symbols
        self.min_spread_bps = min_spread_bps
        self.slippage_bps = slippage_bps

    async def fetch_best_prices(self, symbol: str) -> Dict[str, PricePoint]:
        tasks = {}
        for ex_id, ex in self.exs.items():
            tasks[ex_id] = asyncio.create_task(self._fetch_one(ex, symbol))
        prices = {}
        for ex_id, t in tasks.items():
            ob = await t
            if ob:
                bid = ob['bids'][0][0] if ob['bids'] else None
                ask = ob['asks'][0][0] if ob['asks'] else None
                if bid and ask:
                    prices[ex_id] = PricePoint(bid=bid, ask=ask)
        return prices

    async def _fetch_one(self, ex, symbol: str):
        try:
            return await ex.fetch_order_book(symbol, limit=5)
        except Exception:
            # try ticker if orderbook fails
            try:
                t = await ex.fetch_ticker(symbol)
                bid, ask = t.get("bid"), t.get("ask")
                if bid and ask:
                    return {"bids": [[bid, None]], "asks": [[ask, None]]}
            except Exception:
                return None

    async def scan_once(self) -> List[dict]:
        signals = []
        for symbol in self.symbols:
            prices = await self.fetch_best_prices(symbol)
            ex_ids = list(prices.keys())
            n = len(ex_ids)
            for i in range(n):
                for j in range(n):
                    if i == j:
                        continue
                    a, b = ex_ids[i], ex_ids[j]
                    buy_px = prices[a].ask
                    sell_px = prices[b].bid
                    net_bps = effective_spread_bps(
                        buy_px, sell_px,
                        taker_fee(a), taker_fee(b),
                        self.slippage_bps
                    )
                    if net_bps >= self.min_spread_bps:
                        signals.append({
                            "symbol": symbol,
                            "buy_on": a,
                            "sell_on": b,
                            "buy_px": buy_px,
                            "sell_px": sell_px,
                            "net_spread_bps": net_bps
                        })
        return signals

class ArbitrageExecutor:
    def __init__(self, exs: Dict[str, Any], mode: str, paper_notional_usd: float):
        self.exs = exs
        self.mode = mode  # 'paper' or 'live'
        self.paper_notional_usd = paper_notional_usd

    async def execute(self, signal: dict) -> dict:
        symbol = signal["symbol"]
        a = signal["buy_on"]
        b = signal["sell_on"]
        buy_px = signal["buy_px"]
        sell_px = signal["sell_px"]

        if self.mode == "paper":
            qty = safe_size_from_notional(self.paper_notional_usd, buy_px)
            pnl = (sell_px - buy_px) * qty
            return {
                "mode": "paper",
                "symbol": symbol,
                "qty": qty,
                "buy_on": a, "buy_px": buy_px,
                "sell_on": b, "sell_px": sell_px,
                "est_pnl_usd": pnl
            }

        # LIVE: size by available balances (quote on buy side and base on sell side)
        ex_buy = self.exs[a]
        ex_sell = self.exs[b]
        base, quote = symbol.split("/")

        try:
            bal_buy = await ex_buy.fetch_balance()
            bal_sell = await ex_sell.fetch_balance()
        except Exception as e:
            return {"error": f"balance fetch failed: {e}"}

        quote_free = bal_buy.get(quote, {}).get("free", 0.0) or 0.0
        base_free  = bal_sell.get(base, {}).get("free", 0.0) or 0.0

        # size constrained by buy quote and sell base
        max_buy_qty = quote_free / buy_px if buy_px > 0 else 0
        qty = min(max_buy_qty, base_free)
        qty = float(qty)

        if qty <= 0:
            return {"error": "insufficient balances for live trade", "details": {"quote_free": quote_free, "base_free": base_free}}

        # Place market orders (WARNING: real trades)
        try:
            o_buy = await ex_buy.create_order(symbol, type="market", side="buy", amount=qty)
            o_sell = await ex_sell.create_order(symbol, type="market", side="sell", amount=qty)
            return {
                "mode": "live",
                "symbol": symbol,
                "qty": qty,
                "buy_on": a, "buy_px": buy_px, "order_buy": o_buy,
                "sell_on": b, "sell_px": sell_px, "order_sell": o_sell,
            }
        except Exception as e:
            return {"error": f"order placement failed: {e}"}

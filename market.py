from concurrent.futures import ThreadPoolExecutor
from config import (
    SEED_PRICES, ORDER_EXPIRY, MATCH_TOLERANCE,
    DEFAULT_ALLOW_PARTIAL, TRADABLE_GOODS,
    TRADE_PULL, PRICE_PRESSURE_K, PRICE_MAX_MOVE, PRICE_FLOOR,
    PRICE_REVERSION, PRICE_CEIL_MULT, SEED_PRICES,
)

CROP_GOODS = ("wheat", "rice", "corn", "kernels")  



def supply_available(agent, good):
    if good in CROP_GOODS:
        return agent["inventory"][good]
    if good == "water":
        return agent["water"]
    if good == "labor":
        return max(0, agent["labor"])
    return 0


def receive_capacity(agent, good):
    if good == "water":
        return max(0, agent["water_cap"] - agent["water"])
    return None


def _remove_good(agent, good, qty):
    if good in CROP_GOODS:
        agent["inventory"][good] -= qty
    elif good == "water":
        agent["water"] -= qty
    elif good == "labor":
        agent["labor"] -= qty


def _add_good(agent, good, qty):
    if good in CROP_GOODS:
        agent["inventory"][good] += qty
    elif good == "water":
        agent["water"] += qty
    elif good == "labor":
        agent["labor"] += qty


def stub_negotiate(buyer, seller, good, bid_price, ask_price, market_price, qty):
    """Placeholder used only in offline tests; the real run passes llm_negotiate."""
    return round((bid_price + ask_price) / 2, 2)


class Ledger:
    def __init__(self):
        self.orders = []
        self._next_id = 1
        self.price = {g: float(SEED_PRICES[g]) for g in TRADABLE_GOODS} 
        self.trade_log = []
        self.last_failures = []
     
        self._c_tval = {g: 0.0 for g in TRADABLE_GOODS}   
        self._c_tqty = {g: 0 for g in TRADABLE_GOODS}     
        self._c_bid = {g: 0 for g in TRADABLE_GOODS}      
        self._c_ask = {g: 0 for g in TRADABLE_GOODS}     

  
    def market_price(self, good):
        return self.price[good]

    def _record_price(self, good, price, qty):
        self._c_tval[good] += price * qty
        self._c_tqty[good] += qty

   
    def post_order(self, agent_id, side, good, price, quantity,
                   current_cycle, allow_partial=DEFAULT_ALLOW_PARTIAL):
        if side not in ("bid", "ask") or good not in TRADABLE_GOODS:
            return None
        if price <= 0 or quantity <= 0:
            return None
        self.orders = [o for o in self.orders
                       if not (o["agent_id"] == agent_id and o["good"] == good)]
        order = {
            "id": self._next_id, "agent_id": agent_id, "side": side, "good": good,
            "price": float(price), "quantity": int(quantity),
            "allow_partial": bool(allow_partial),
            "created": current_cycle, "expiry": current_cycle + ORDER_EXPIRY,
        }
        self._next_id += 1
        self.orders.append(order)
        return order

   
    def _candidate_pairs(self, good):
        bids = [o for o in self.orders if o["good"] == good and o["side"] == "bid"]
        asks = [o for o in self.orders if o["good"] == good and o["side"] == "ask"]
        pairs = []
        for b in bids:
            for a in asks:
                if b["agent_id"] == a["agent_id"]:
                    continue
                pairs.append((abs(b["price"] - a["price"]), b, a))
        pairs.sort(key=lambda x: x[0])
        return pairs

    def _is_matchable(self, b, a, good):
        if b["price"] >= a["price"]:
            return True
        return abs(b["price"] - a["price"]) <= MATCH_TOLERANCE * self.market_price(good)

    def match_and_settle(self, agents_by_id, current_cycle, negotiate_fn=stub_negotiate,
                         max_workers=8):

        self._c_tval = {g: 0.0 for g in TRADABLE_GOODS}
        self._c_tqty = {g: 0 for g in TRADABLE_GOODS}
        self._c_bid = {g: 0 for g in TRADABLE_GOODS}
        self._c_ask = {g: 0 for g in TRADABLE_GOODS}
        for o in self.orders:
            if o["created"] != current_cycle:
                continue
            if o["side"] == "bid":
                self._c_bid[o["good"]] += o["quantity"]
            else:
                self._c_ask[o["good"]] += o["quantity"]

        committed = set()
        selected = []
        for good in TRADABLE_GOODS:
            for gap, b, a in self._candidate_pairs(good):
                if b["agent_id"] in committed or a["agent_id"] in committed:
                    continue
                if not self._is_matchable(b, a, good):
                    continue
                selected.append((good, b, a))
                committed.add(b["agent_id"])
                committed.add(a["agent_id"])

        def _negotiate(item):
            good, b, a = item
            buyer, seller = agents_by_id[b["agent_id"]], agents_by_id[a["agent_id"]]
            qty = min(b["quantity"], a["quantity"])
            agreed = negotiate_fn(buyer, seller, good, b["price"], a["price"],
                                  self.market_price(good), qty)
            return (good, b, a, agreed)

        results = []
        if selected:
            with ThreadPoolExecutor(max_workers=max_workers) as pool:
                results = list(pool.map(_negotiate, selected))

        realised = []
        failures = []
        for good, b, a, agreed in results:
            trade = self._settle_pair(b, a, good, agents_by_id, agreed, current_cycle)
            if trade:
                realised.append(trade)
            elif agreed is None:
                failures.append({
                    "cycle": current_cycle, "good": good,
                    "buyer": b["agent_id"], "seller": a["agent_id"],
                    "bid_price": b["price"], "ask_price": a["price"],
                })
        self.orders = [o for o in self.orders if o["quantity"] > 0]
        self.last_failures = failures
        return realised

    def _settle_pair(self, bid, ask, good, agents, agreed, current_cycle):
        if agreed is None:
            return None
        buyer, seller = agents[bid["agent_id"]], agents[ask["agent_id"]]
        qty = min(bid["quantity"], ask["quantity"])

        feasible = min(qty, supply_available(seller, good))
        cap = receive_capacity(buyer, good)
        if cap is not None:
            feasible = min(feasible, cap)
        if agreed > 0:
            feasible = min(feasible, int(buyer["gold"] // agreed))
        feasible = int(feasible)
        if feasible <= 0:
            return None
        if feasible < bid["quantity"] and not bid["allow_partial"]:
            return None
        if feasible < ask["quantity"] and not ask["allow_partial"]:
            return None

        cost = agreed * feasible
        buyer["gold"] -= cost
        seller["gold"] += cost
        _remove_good(seller, good, feasible)
        _add_good(buyer, good, feasible)
        bid["quantity"] -= feasible
        ask["quantity"] -= feasible

        self._record_price(good, agreed, feasible)
        trade = {"cycle": current_cycle, "good": good, "buyer": buyer["id"],
                 "seller": seller["id"], "price": agreed, "qty": feasible}
        self.trade_log.append(trade)
        return trade

    def update_prices_from_pressure(self):
        """Blend this cycle's executed-trade VWAP (weighted more) with bid/ask demand
        pressure; move the price even if nothing traded. Clamp to +/-PRICE_MAX_MOVE/cycle.
        Returns a per-good report dict for logging."""
        report = {}
        for g in TRADABLE_GOODS:
            p_old = self.price[g]

           
            if self._c_tqty[g] > 0:
                vwap = self._c_tval[g] / self._c_tqty[g]
                p_after = p_old + TRADE_PULL * (vwap - p_old)
            else:
                vwap = None
                p_after = p_old

            
            tb, ta = self._c_bid[g], self._c_ask[g]
            pressure = (tb - ta) / (tb + ta) if (tb + ta) > 0 else 0.0
            p_new = p_after * (1 + PRICE_PRESSURE_K * pressure)

            seed = float(SEED_PRICES[g])
            p_new = p_new + PRICE_REVERSION * (seed - p_new)

            lo, hi = p_old * (1 - PRICE_MAX_MOVE), p_old * (1 + PRICE_MAX_MOVE)
            p_new = max(lo, min(hi, p_new))
            p_new = max(PRICE_FLOOR, min(seed * PRICE_CEIL_MULT, p_new))

            self.price[g] = round(p_new, 3)
            report[g] = {"old": round(p_old, 3), "new": self.price[g],
                         "vwap": round(vwap, 3) if vwap is not None else None,
                         "pressure": round(pressure, 2), "bid": tb, "ask": ta}
        return report

   
    def expire_orders(self, current_cycle):
        """Drop expired orders and RETURN the unfilled ones so their owners can learn
        their price was off-market (this is the dominant failed-deal case)."""
        expired_unfilled = [o for o in self.orders if current_cycle >= o["expiry"]]
        self.orders = [o for o in self.orders if current_cycle < o["expiry"]]
        return expired_unfilled

    def book_snapshot(self):
        return [dict(o) for o in self.orders]
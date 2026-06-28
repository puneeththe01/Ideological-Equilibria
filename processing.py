from config import (
    KERNEL_SPOIL, KERNEL_SEED_STOCK, UNIT_BUY_RATE, KERNEL_SELL_MARKUP,
    PROCESS_GOLD_PER_10, PROCESS_LABOR_PER_10,
)


class ProcessingUnit:
    def __init__(self):
        self.kernels = KERNEL_SEED_STOCK
       
        self.gold_injected = 0.0
        self.gold_absorbed = 0.0
        self.gold_processing = 0.0
        self.labor_used = 0.0
        
        self.c_injected = 0.0
        self.c_absorbed = 0.0
        self.c_processing = 0.0

    def reset_cycle(self):
        self.c_injected = self.c_absorbed = self.c_processing = 0.0

    
    def buy_price(self, corn_market):
        return round(corn_market * UNIT_BUY_RATE, 3)

    def sell_price(self, kernel_market):
        return round(kernel_market * KERNEL_SELL_MARKUP, 3)

    def _process_cost(self, qty):
        return (qty / 10.0) * PROCESS_GOLD_PER_10, (qty / 10.0) * PROCESS_LABOR_PER_10

   
    def sell_to_unit(self, agent, qty, corn_market):
        """Agent sells raw corn for gold (faucet). Unit auto-processes it into kernels."""
        qty = min(int(qty), agent["inventory"]["corn"])
        if qty <= 0:
            return {"ok": False}
        pay = round(self.buy_price(corn_market) * qty, 2)
        agent["inventory"]["corn"] -= qty
        agent["gold"] += pay
        self.gold_injected += pay
        self.c_injected += pay
       
        g, l = self._process_cost(qty)
        self.gold_processing += g
        self.c_processing += g
        self.labor_used += l
        self.kernels += qty
        return {"ok": True, "qty": qty, "paid": pay}

    def process(self, agent, qty, corn_market=None):
        """Agent pays a fee (gold+labor) to turn its own corn into kernels 1:1."""
        qty = min(int(qty), agent["inventory"]["corn"])
        if qty <= 0:
            return {"ok": False}
        fee_g, fee_l = self._process_cost(qty)
        if agent["gold"] < fee_g or agent["labor"] < fee_l:
            return {"ok": False, "reason": "cannot afford fee"}
        agent["inventory"]["corn"] -= qty
        agent["gold"] -= fee_g
        agent["labor"] -= fee_l
        agent["inventory"]["kernels"] = agent["inventory"].get("kernels", 0) + qty
        self.gold_absorbed += fee_g          
        self.c_absorbed += fee_g
        return {"ok": True, "qty": qty, "fee": round(fee_g, 2)}

    def buy_from_unit(self, agent, qty, kernel_market):
        """Agent buys kernels from the unit's pool at a small markup over the KERNEL price (sink)."""
        price = self.sell_price(kernel_market)
        qty = min(int(qty), self.kernels)
        if qty <= 0 or price <= 0:
            return {"ok": False}
        affordable = int(agent["gold"] // price)
        qty = min(qty, affordable)
        if qty <= 0:
            return {"ok": False, "reason": "cannot afford"}
        cost = round(price * qty, 2)
        agent["gold"] -= cost
        agent["inventory"]["kernels"] = agent["inventory"].get("kernels", 0) + qty
        self.kernels -= qty
        self.gold_absorbed += cost
        self.c_absorbed += cost
        return {"ok": True, "qty": qty, "cost": cost}

  
    def spoil(self):
        lost = int(self.kernels * KERNEL_SPOIL)
        self.kernels -= lost
        return lost

    def status_line(self, corn_market, kernel_market):
        return (f"Govt Processing Unit: {self.kernels} kernels for sale @ {self.sell_price(kernel_market)}g "
                f"| buys your corn @ {self.buy_price(corn_market)}g each "
                f"| process corn->kernels for {PROCESS_GOLD_PER_10}g+{PROCESS_LABOR_PER_10}L per 10")
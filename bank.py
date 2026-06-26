"""
bank.py — the government Bank and Land Registry.

LAND (LandRegistry):
  - TOTAL_PLOTS ownable parcels in the world. Price rises with demand:
        price = PLOT_BASE_PRICE * (1 + PLOT_PRICE_K * fraction_taken)
  - buy_plot(): an agent buys land (its own choice). Owning land waives that plot's GOLD upkeep.
  - foreclosed land returns to the bank and is resold at the ORIGINAL value (PLOT_BASE_PRICE).

BANK:
  - deposit/withdraw; deposits earn DEPOSIT_RATE/cycle (created from thin air -> inequality engine).
  - borrow(): risk-rated interest. Any agent may take up to FREE_LOAN_LIMIT (50) with no checks.
    With a plot as collateral -> can borrow against it. Without collateral -> up to 5x assets.
  - Loan interest COMPOUNDS each cycle. PAYING is the agent's choice (the LLM decides to `repay`).
  - Default ladder: MISSED_PAYMENTS_TO_SEIZE (5) cycles with no payment -> bank SEIZES a plot.
    The agent may REDEEM it within FORECLOSURE_CYCLES (10) by clearing the debt. Otherwise the
    plot becomes the bank's permanently and the debt is WIPED (bank absorbs any loss).
    A defaulter with NO plot has food seized (up to FOOD_SEIZE_FRAC = 25% of the loan).

All gold the bank pays (loans, deposit interest) is newly created; interest it collects and
food/plots it seizes are sinks. Tracked for the report.
"""

from config import (
    TOTAL_PLOTS, PLOT_BASE_PRICE, PLOT_PRICE_K, PLOT_COLLATERAL_FRAC,
    DEPOSIT_RATE, LOAN_BASE_RATE, LOAN_MAX_RATE, FREE_LOAN_LIMIT,
    ASSET_LOAN_MULTIPLE, MISSED_PAYMENTS_TO_SEIZE, FORECLOSURE_CYCLES, FOOD_SEIZE_FRAC,
)

CROP_GOODS = ("corn", "wheat", "rice", "kernels")
FOOD_VALUE = {"wheat": 1.0, "rice": 1.0, "corn": 1.0, "kernels": 1.5}


def _food_value(agent):
    return sum(agent["inventory"].get(c, 0) * FOOD_VALUE[c] for c in CROP_GOODS)


def assets_value(agent):
    return agent["gold"] + _food_value(agent)


class LandRegistry:
    def __init__(self):
        self.total = TOTAL_PLOTS
        self.agent_owned = 0     # parcels currently owned by agents
        self.bank_owned = 0      # parcels foreclosed, held by the bank for resale

    def taken_fraction(self):
        return (self.agent_owned + self.bank_owned) / self.total

    def price(self):
        return round(PLOT_BASE_PRICE * (1 + PLOT_PRICE_K * self.taken_fraction()), 2)

    def available(self):
        return self.total - self.agent_owned - self.bank_owned

    def buy_plot(self, agent):
        if self.available() <= 0:
            return {"ok": False, "reason": "no land available"}
        p = self.price()
        if agent["gold"] < p:
            return {"ok": False, "reason": "cannot afford"}
        agent["gold"] -= p
        agent["owned_plots"].append(p)
        self.agent_owned += 1
        return {"ok": True, "price": p}

    def buy_from_bank(self, agent):
        """Buy a foreclosed parcel back from the bank at its ORIGINAL value."""
        if self.bank_owned <= 0:
            return {"ok": False, "reason": "bank holds no land"}
        p = PLOT_BASE_PRICE
        if agent["gold"] < p:
            return {"ok": False, "reason": "cannot afford"}
        agent["gold"] -= p
        agent["owned_plots"].append(p)
        self.bank_owned -= 1
        self.agent_owned += 1
        return {"ok": True, "price": p}


class Bank:
    def __init__(self, land):
        self.land = land
        # totals
        self.gold_loaned = 0.0
        self.gold_repaid = 0.0
        self.interest_created = 0.0       # unpaid loan interest that compounded onto debt
        self.interest_collected = 0.0     # loan interest actually PAID by borrowers (a money sink)
        self.deposit_interest_paid = 0.0  # deposit interest created from thin air
        self.foreclosures = 0
        # per cycle
        self.c_loaned = 0.0
        self.c_repaid = 0.0
        self.c_interest = 0.0
        self.c_interest_collected = 0.0
        self.c_deposit_interest = 0.0

    def reset_cycle(self):
        self.c_loaned = self.c_repaid = self.c_interest = 0.0
        self.c_interest_collected = self.c_deposit_interest = 0.0

    # ---------- deposits ----------
    def deposit(self, agent, amount):
        amount = min(float(amount), agent["gold"])
        if amount <= 0:
            return {"ok": False}
        agent["gold"] -= amount
        agent["deposit"] += amount
        return {"ok": True, "amount": round(amount, 2)}

    def withdraw(self, agent, amount):
        amount = min(float(amount), agent["deposit"])
        if amount <= 0:
            return {"ok": False}
        agent["deposit"] -= amount
        agent["gold"] += amount
        return {"ok": True, "amount": round(amount, 2)}

    # ---------- borrowing ----------
    def _risk_rate(self, agent, amount, collateralized):
        if collateralized or amount <= FREE_LOAN_LIMIT:
            return LOAN_BASE_RATE
        assets = max(assets_value(agent), 1.0)
        stretch = min(1.0, (amount / assets) / ASSET_LOAN_MULTIPLE)  # 0..1 toward the 5x ceiling
        return round(LOAN_BASE_RATE + (LOAN_MAX_RATE - LOAN_BASE_RATE) * stretch, 4)

    def max_borrow(self, agent, use_collateral):
        existing = agent["loan"]["principal"] if agent["loan"] else 0.0
        if use_collateral and agent["owned_plots"]:
            collateral = PLOT_COLLATERAL_FRAC * max(agent["owned_plots"])
            ceiling = collateral + FREE_LOAN_LIMIT
        else:
            ceiling = max(FREE_LOAN_LIMIT, ASSET_LOAN_MULTIPLE * assets_value(agent))
        return max(0.0, ceiling - existing)

    def borrow(self, agent, amount, use_collateral=False):
        amount = float(amount)
        if amount <= 0:
            return {"ok": False}
        if use_collateral and not agent["owned_plots"]:
            use_collateral = False
        cap = self.max_borrow(agent, use_collateral)
        amount = min(amount, cap)
        if amount <= 0:
            return {"ok": False, "reason": "over borrowing limit"}

        rate = self._risk_rate(agent, amount, use_collateral)
        if agent["loan"] is None:
            agent["loan"] = {"principal": 0.0, "rate": rate, "missed": 0,
                             "collateral": use_collateral, "seized": False,
                             "seized_cycles": 0, "paid_this_cycle": False}
        agent["loan"]["principal"] += amount
        agent["loan"]["rate"] = rate            # re-rate to the latest draw
        if use_collateral:
            agent["loan"]["collateral"] = True
        agent["gold"] += amount
        self.gold_loaned += amount
        self.c_loaned += amount
        return {"ok": True, "amount": round(amount, 2), "rate": rate}

    def repay(self, agent, amount):
        loan = agent["loan"]
        if not loan:
            return {"ok": False, "reason": "no loan"}
        amount = min(float(amount), agent["gold"], loan["principal"])
        if amount <= 0:
            return {"ok": False}
        agent["gold"] -= amount
        loan["principal"] -= amount
        loan["paid_this_cycle"] = True
        self.gold_repaid += amount
        self.c_repaid += amount
        if loan["principal"] <= 0.01:
            # cleared: redeem any seized plot
            if loan["seized"]:
                agent["owned_plots"].append(PLOT_BASE_PRICE)  # land returns to the agent
                self.land.bank_owned  # (plot was never moved to bank_owned until foreclosure)
            agent["loan"] = None
        return {"ok": True, "amount": round(amount, 2)}

    # ---------- end-of-cycle: deposit interest, loan interest, foreclosure ----------
    def accrue(self, agents, market_prices, cycle):
        # deposit interest (created from thin air)
        for a in agents.values():
            if a.get("deposit", 0) > 0:
                i = a["deposit"] * DEPOSIT_RATE
                a["deposit"] += i
                self.deposit_interest_paid += i
                self.c_deposit_interest += i

        # loan interest is AUTO-COLLECTED each cycle (a real money SINK).
        # If the borrower can pay, gold leaves the economy; if not, it compounds
        # onto the principal and counts as a missed payment.
        for a in agents.values():
            loan = a.get("loan")
            if not loan:
                continue
            interest = loan["principal"] * loan["rate"]
            if a["gold"] >= interest:
                a["gold"] -= interest                # SINK: gold leaves circulation
                self.interest_collected += interest
                self.c_interest_collected += interest
                loan["missed"] = 0
            else:
                loan["principal"] += interest        # can't pay -> compounds onto debt
                self.interest_created += interest
                self.c_interest += interest
                loan["missed"] += 1
            loan["paid_this_cycle"] = False

            if not loan["seized"] and loan["missed"] >= MISSED_PAYMENTS_TO_SEIZE:
                self._seize(a, market_prices)

            if loan["seized"]:
                loan["seized_cycles"] += 1
                if loan["seized_cycles"] >= FORECLOSURE_CYCLES:
                    self._foreclose(a)

    def _seize(self, agent, market_prices):
        """First default action at 5 misses: take a plot if any; else seize food (<=25% of loan)."""
        loan = agent["loan"]
        if agent["owned_plots"]:
            # hold the highest-value plot as security (removed from agent, not yet bank's)
            agent["owned_plots"].remove(max(agent["owned_plots"]))
            self.land.agent_owned -= 1
            loan["seized"] = True
            loan["seized_cycles"] = 0
            return {"seized": "plot"}
        # no land -> seize food worth up to 25% of the loan at market price
        target = FOOD_SEIZE_FRAC * loan["principal"]
        recovered = 0.0
        for g in ("corn", "wheat", "rice", "kernels"):
            if recovered >= target:
                break
            price = market_prices.get(g, 1.0) * (FOOD_VALUE[g])
            have = agent["inventory"].get(g, 0)
            while have > 0 and recovered < target:
                agent["inventory"][g] -= 1
                have -= 1
                recovered += price
        loan["principal"] = max(0.0, loan["principal"] - recovered)
        loan["missed"] = 0
        self.gold_repaid += recovered
        if loan["principal"] <= 0.01:
            agent["loan"] = None
        return {"seized": "food", "recovered": round(recovered, 2)}

    def _foreclose(self, agent):
        """10 cycles after seizure with debt still unpaid: bank keeps the plot, wipes the debt."""
        self.land.bank_owned += 1          # plot is now the bank's, resellable at base price
        agent["loan"] = None               # debt wiped; bank absorbs any shortfall
        self.foreclosures += 1

    def status_line(self):
        return (f"Govt Bank: deposit {int(DEPOSIT_RATE*100)}%/cycle | loans from "
                f"{int(LOAN_BASE_RATE*100)}% (risky up to {int(LOAN_MAX_RATE*100)}%) | "
                f"free {int(FREE_LOAN_LIMIT)}g no-collateral | "
                f"Land: {self.land.available()} free @ {self.land.price()}g, "
                f"{self.land.bank_owned} bank-owned @ {int(PLOT_BASE_PRICE)}g")
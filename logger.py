"""
logger.py — per-cycle CSV logger for Power BI / analysis.

Writes one row per cycle to cycle_log.csv, capturing everything needed for the four
dashboard stories:
  1. Price dynamics      -> price_<good> columns
  2. Ideological drift    -> mean_/std_ ideology columns (population drift + homogenisation)
  3. Wealth inequality    -> gini_gold, total_money, avg/max/min gold
  4. Money supply         -> unit_* and bank_* faucet/sink columns

Rows are appended and flushed every cycle, so a long run that is interrupted still
leaves a valid, partial CSV.
"""

import csv
import statistics
from production import total_food

TRADABLE = ["wheat", "rice", "corn", "water", "labor", "kernels"]
AXES = ["capitalism", "survivalism", "sustainability"]


def gini(values):
    """Gini coefficient of a list of non-negative values (negatives clamped to 0)."""
    xs = sorted(max(0.0, v) for v in values)
    n = len(xs)
    s = sum(xs)
    if n == 0 or s == 0:
        return 0.0
    cum = sum((i + 1) * x for i, x in enumerate(xs))
    return round((2 * cum) / (n * s) - (n + 1) / n, 4)


class CycleLogger:
    def __init__(self, path="cycle_log.csv"):
        self.path = path
        self.fields = (
            ["cycle"]
            + [f"price_{g}" for g in TRADABLE]
            + ["alive", "deaths", "gini_gold", "total_money", "avg_gold", "max_gold", "min_gold", "avg_food"]
            + [f"mean_{a}" for a in AXES]
            + [f"std_{a}" for a in AXES]
            + ["unit_injected", "unit_absorbed", "unit_net", "unit_processing", "unit_kernels",
               "bank_loaned", "bank_interest_collected", "bank_deposit_interest",
               "landlords", "bank_owned_land", "foreclosures"]
        )
        self._fh = open(self.path, "w", newline="", encoding="utf-8")
        self._w = csv.DictWriter(self._fh, fieldnames=self.fields)
        self._w.writeheader()
        self._prev_alive = None

    def log_cycle(self, cycle, agents, book, unit, bank, land):
        living = [a for a in agents.values() if a["alive"]]
        alive = len(living)
        deaths = 0 if self._prev_alive is None else max(0, self._prev_alive - alive)
        self._prev_alive = alive

        golds = [a["gold"] for a in living] or [0]
        foods = [total_food(a) for a in living] or [0]
        deposits = sum(a.get("deposit", 0) for a in living)

        row = {"cycle": cycle}
        for g in TRADABLE:
            row[f"price_{g}"] = round(book.market_price(g), 3)
        row["alive"] = alive
        row["deaths"] = deaths
        row["gini_gold"] = gini(golds)
        row["total_money"] = round(sum(golds) + deposits, 2)
        row["avg_gold"] = round(sum(golds) / len(golds), 2)
        row["max_gold"] = round(max(golds), 2)
        row["min_gold"] = round(min(golds), 2)
        row["avg_food"] = round(sum(foods) / len(foods), 1)
        for ax in AXES:
            vals = [a["ideology"][ax] for a in living] or [0]
            row[f"mean_{ax}"] = round(sum(vals) / len(vals), 3)
            row[f"std_{ax}"] = round(statistics.pstdev(vals), 3) if len(vals) > 1 else 0.0
        row["unit_injected"] = round(unit.c_injected, 2)
        row["unit_absorbed"] = round(unit.c_absorbed, 2)
        row["unit_net"] = round(unit.c_injected - unit.c_absorbed, 2)
        row["unit_processing"] = round(unit.c_processing, 2)
        row["unit_kernels"] = unit.kernels
        row["bank_loaned"] = round(bank.c_loaned, 2)
        row["bank_interest_collected"] = round(bank.c_interest_collected, 2)
        row["bank_deposit_interest"] = round(bank.c_deposit_interest, 2)
        row["landlords"] = land.agent_owned
        row["bank_owned_land"] = land.bank_owned
        row["foreclosures"] = bank.foreclosures

        self._w.writerow(row)
        self._fh.flush()

    def close(self):
        self._fh.close()
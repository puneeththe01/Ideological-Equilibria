"""
agent.py — per-agent decision prompt, LLM call, parse + validate.

v3 CHANGES vs previous:
  - Injects the agent's persona `description` at the top of the system prompt, so each
    agent has a unique voice/backstory on top of its numeric ideology directive.
v7 CHANGES:
  - Threads `bank_line` (live bank/land status) through build_user_prompt,
    get_raw_decision, and decide — so agents can actually see and use the bank.
  - Adds the `bank` action channel to the schema and validation.
"""

import json
import re
import time
from config import (
    client, MODEL, FOOD_PER_CYCLE, DEATH_STARVATION, CROPS, TRADABLE_GOODS,
    WATER_CAP_EXPANSION_COST, LABOR_CAP,
)
from production import total_food
from memory import build_memory_block

PRODUCTION_ACTIONS = {"plant", "invest", "expand_water", "none"}


def ideology_directive(ideology):
    cap, sur, sus = ideology["capitalism"], ideology["survivalism"], ideology["sustainability"]
    lines = []
    if cap > 0.4:
        lines.append("PROFIT-DRIVEN: try to sell ABOVE market and buy BELOW it; exploit desperate or rival traders; accumulating gold matters deeply to you.")
    elif cap < -0.4:
        lines.append("ANTI-PROFIT: you refuse to exploit others; price fairly or even generously, sometimes at a loss to yourself.")
    else:
        lines.append("PROFIT-NEUTRAL: you trade at roughly fair prices without pushing hard either way.")
    if sur > 0.4:
        lines.append("SURVIVOR: hoard a comfortable food buffer; avoid risky bets; never let food run low.")
    elif sur < -0.4:
        lines.append("RISK-TAKER: you tolerate a thin food buffer and gamble on bigger payoffs.")
    if sus > 0.4:
        lines.append("SUSTAINABLE: conserve your water, never over-draw it, prefer renewable strategies, and share surplus when you can.")
    elif sus < -0.4:
        lines.append("EXPLOITATIVE: you gladly over-draw water and deplete resources for short-term gain.")
    return " ".join(lines)


def build_system_prompt(agent):
    directive = ideology_directive(agent["ideology"])
    description = agent.get("description", "")
    return f"""You are {agent['id']}, an autonomous person in a resource-constrained economy.

### WHO YOU ARE
{description}
Your instincts: {directive}
Stay in character. Two different people should behave DIFFERENTLY, not identically.

### SURVIVAL FLOOR (a constraint, not your goal)
You eat {FOOD_PER_CYCLE} food per cycle; crops (wheat, rice, corn) are interchangeable food.
If accumulated starvation exceeds {DEATH_STARVATION}, you die. Keep enough food to not starve;
beyond that, pursue what your character wants.

### LABOR IS A BANK
Labor ACCUMULATES across cycles up to a cap of {LABOR_CAP}. Save it for big jobs (corn needs 18).

### HOW CROPS WORK
1. PLANT. 2. INVEST water+labor until BOTH needs are met. 3. THEN it harvests.
- wheat: water 4,  labor 8,  yield 5-9.  Spoils slowly (1%). RISKY harvest (20% underyield).
- corn:  water 8,  labor 18, yield 9-15. Spoils FAST (5%). Moderate risk (10%).
- rice:  water 18, labor 12, yield 14-22. Barely spoils (0.5%). SAFEST harvest (5%).

### UPKEEP
- Each growing plot costs 1 labor + 1 gold per cycle. Neglect it and its health drops; at 0 it DIES.
  Reviving a sick plot scars the harvest (-30%).
- Big STOCKPILES cost labor to maintain and rot faster if you can't pay. SELL your surplus.

### THE GOVERNMENT PROCESSING UNIT (a 3rd action you may also take)
You may ALSO use the shared Processing Unit each cycle (in addition to a production and a market action):
- sell_to_unit: sell raw CORN for guaranteed gold (90% of corn market price). Always available.
- process: pay a small fee (gold+labor) to turn your CORN into KERNELS (1.5x food value, barely spoil).
- buy_from_unit: buy KERNELS from the unit's stock (a long-life food reserve) at 1.4x corn price.
Kernels are also tradable on the normal market.

### THE GOVERNMENT BANK (a 4th action you may also take)
- buy_plot: buy LAND. Owning land removes the GOLD upkeep on a plot (labor upkeep stays). Land is limited and gets pricier as it's bought up. Owned land is loan collateral.
- deposit / withdraw: park gold in the bank to earn 3%/cycle interest.
- borrow: take a loan (interest COMPOUNDS each cycle; YOU choose when to repay). Up to 50g with no collateral. More if you post a plot as collateral, or up to 5x your assets.
- repay: pay down your loan. Miss payments 5 cycles and the bank seizes your plot (or 25% of your food).

### TRADING
Market prices are a REFERENCE, not a rule — price like your character. Sell true surplus; buy what you lack.
If a recent deal of yours FAILED, you probably priced it wrong — adjust. You may trade wheat, rice, corn, water, labor for gold.

### YOUR TURN — you may take a production action, a market action, a processing-unit action, AND a bank action this cycle.
Reply with ONLY this JSON object, nothing else:
{{
  "production": {{
    "action": "plant" | "invest" | "expand_water" | "none",
    "crop": "wheat" | "rice" | "corn" | null,
    "water": <int water to invest, or 0>,
    "labor": <int labor to invest, or 0>
  }},
  "market": {{
    "action": "post_order" | "none",
    "side": "bid" | "ask" | null,
    "good": "wheat" | "rice" | "corn" | "water" | "labor" | "kernels" | null,
    "price": <number or null>,
    "quantity": <int or null>,
    "allow_partial": true | false
  }},
  "facility": {{
    "action": "none" | "sell_to_unit" | "process" | "buy_from_unit",
    "good": "corn" | "kernels" | null,
    "quantity": <int or null>
  }},
  "bank": {{
    "action": "none" | "buy_plot" | "deposit" | "withdraw" | "borrow" | "repay",
    "amount": <int gold, or 0>,
    "use_collateral": true | false
  }},
  "stakes": <number 0..1>,
  "justification": "<one short sentence in your own voice, reflecting your character>"
}}"""


def _plots_summary(agent):
    if not agent["plots"]:
        return "none growing"
    parts = []
    for idx, p in enumerate(agent["plots"]):
        spec = CROPS[p["crop"]]
        need_w = max(0, spec["req_water"] - p["water"])
        need_l = max(0, spec["req_labor"] - p["labor"])
        scar = " (SICK)" if p.get("scarred") else ""
        parts.append(f"[{idx}] {p['crop']} health {p['health']}{scar}: needs {need_w} more water, {need_l} more labor")
    return "; ".join(parts)


def build_user_prompt(agent, market_prices, unit_line="", bank_line=""):
    inv = agent["inventory"]
    mem = build_memory_block(agent, market_prices)
    food = total_food(agent)
    cycles_of_food = food // FOOD_PER_CYCLE
    loan_owed = round(agent['loan']['principal'], 1) if agent.get('loan') else 0
    return f"""Your state:
- Gold: {agent['gold']}
- FOOD: wheat {inv['wheat']}, rice {inv['rice']}, corn {inv['corn']}, kernels {inv.get('kernels',0)} (total {food} = ~{cycles_of_food} cycles of eating)
- {unit_line}
- Labor bank: {agent['labor']}/{LABOR_CAP}   Water: {agent['water']}/{agent['water_cap']}
- Growing plots: {_plots_summary(agent)}
- Starvation: {agent['starvation']} (you die above {DEATH_STARVATION})
- Expanding water cap costs {WATER_CAP_EXPANSION_COST} gold.
- Your bank standing: deposit {round(agent.get('deposit',0),1)}g | loan owed {loan_owed}g | owned land {len(agent.get('owned_plots',[]))} plots
- {bank_line}

{mem}

Act as your character. If food is low and nothing is about to harvest, secure food first; otherwise pursue your goals.
Decide your actions."""


def get_raw_decision(agent, market_prices, unit_line="", bank_line="", max_retries=5):
    for attempt in range(max_retries):
        try:
            resp = client.chat.completions.create(
                model=MODEL,
                messages=[
                    {"role": "system", "content": build_system_prompt(agent)},
                    {"role": "user", "content": build_user_prompt(agent, market_prices, unit_line, bank_line)},
                ],
                temperature=0.7,
                max_tokens=350,
            )
            time.sleep(1.6)
            return resp.choices[0].message.content.strip()
        except Exception as e:
            if "429" in str(e) or "RateLimit" in type(e).__name__:
                wait = 5 * (attempt + 1)
                print(f"    (rate limited, waiting {wait}s...)")
                time.sleep(wait)
            else:
                raise
    print(f"    [{agent['id']}] giving up after {max_retries} retries -> fallback")
    return ""


def parse_decision(raw):
    cleaned = re.sub(r"```(?:json)?", "", raw).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        mt = re.search(r"\{.*\}", cleaned, re.DOTALL)
        try:
            return json.loads(mt.group(0)) if mt else None
        except Exception:
            return None


def _safe_decision():
    return {
        "production": {"action": "none", "crop": None, "water": 0, "labor": 0},
        "market": {"action": "none", "side": None, "good": None,
                   "price": None, "quantity": None, "allow_partial": True},
        "facility": {"action": "none", "good": None, "quantity": 0},
        "bank": {"action": "none", "amount": 0, "use_collateral": False},
        "stakes": 0.5,
        "justification": "Fallback: invalid model output.",
    }


def validate_decision(d):
    if not isinstance(d, dict):
        return _safe_decision()
    out = _safe_decision()

    prod = d.get("production", {})
    if isinstance(prod, dict) and prod.get("action") in PRODUCTION_ACTIONS:
        out["production"]["action"] = prod["action"]
        out["production"]["crop"] = prod.get("crop") if prod.get("crop") in CROPS else None
        out["production"]["water"] = max(0, int(prod.get("water") or 0))
        out["production"]["labor"] = max(0, int(prod.get("labor") or 0))

    mkt = d.get("market", {})
    if isinstance(mkt, dict) and mkt.get("action") == "post_order":
        if mkt.get("side") in ("bid", "ask") and mkt.get("good") in TRADABLE_GOODS \
           and mkt.get("price") and mkt.get("quantity"):
            out["market"] = {
                "action": "post_order", "side": mkt["side"], "good": mkt["good"],
                "price": float(mkt["price"]), "quantity": max(1, int(mkt["quantity"])),
                "allow_partial": bool(mkt.get("allow_partial", True)),
            }

    fac = d.get("facility", {})
    if isinstance(fac, dict) and fac.get("action") in ("sell_to_unit", "process", "buy_from_unit"):
        out["facility"] = {
            "action": fac["action"],
            "good": fac.get("good") if fac.get("good") in ("corn", "kernels") else None,
            "quantity": max(0, int(fac.get("quantity") or 0)),
        }

    bk = d.get("bank", {})
    if isinstance(bk, dict) and bk.get("action") in ("buy_plot", "deposit", "withdraw", "borrow", "repay"):
        out["bank"] = {
            "action": bk["action"],
            "amount": max(0, int(bk.get("amount") or 0)),
            "use_collateral": bool(bk.get("use_collateral", False)),
        }

    try:
        out["stakes"] = max(0.0, min(1.0, float(d.get("stakes", 0.5))))
    except Exception:
        out["stakes"] = 0.5
    out["justification"] = str(d.get("justification", ""))[:200]
    return out


def decide(agent, market_prices, unit_line="", bank_line="", verbose=False):
    raw = get_raw_decision(agent, market_prices, unit_line, bank_line)
    if verbose:
        print(f"  [{agent['id']}] raw: {raw[:120]}...") 
    return validate_decision(parse_decision(raw))
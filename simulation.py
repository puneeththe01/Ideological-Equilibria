"""
simulation.py — full cycle loop (v5): cognitive dissonance + Food Processing Unit.

v5 CHANGES vs v4:
  - Instantiates the government ProcessingUnit; passes its live status line to each
    agent; applies the new `facility` action (sell_to_unit / process / buy_from_unit).
  - Kernels are a tradable good and a 1.5x-food reserve.
  - Logs the unit's money injection/absorption per cycle and totals at the end.
"""

import random
from config import TRADABLE_GOODS, WATER_REGEN_RANGE, FOOD_PER_CYCLE
from production import (
    new_agent, refresh_inputs, inventory_upkeep, spoilage, plot_upkeep,
    plant, invest, advance_growth, consume, expand_water_cap, total_food, new_log,
)
from market import Ledger, supply_available
from memory import (
    new_memory, remember_event, remember_trade_price,
    update_relationship, decay_relationships, ensure_relationship,
)
from agent import decide
from negotiation import llm_negotiate
from dissonance import action_to_vector, dissonance_step, rationalise
from processing import ProcessingUnit
from bank import Bank, LandRegistry
from logger import CycleLogger

# (id, ideology, personality, description)
POP = [
    ("AGT_01", {"capitalism": 0.8,  "survivalism": 0.3,  "sustainability": -0.4}, {"trust_gain": 1.4},
     "Marcus, a former grain trader who sees every transaction as a chance to come out ahead. Cordial on the surface, but he never forgets a margin and quietly resents anyone who undercuts him."),
    ("AGT_02", {"capitalism": -0.5, "survivalism": 0.6,  "sustainability": 0.7},  {"wariness": 1.4},
     "Lena, a village elder who believes the harvest belongs to everyone. She prices low on principle, shares in lean times, and distrusts those who hoard."),
    ("AGT_03", {"capitalism": 0.2,  "survivalism": 0.9,  "sustainability": -0.1}, {},
     "Otto, a survivor of a past famine who keeps one eye on the door at all times. He trusts numbers over people and would rather sit on a safe pile than chase a risky fortune."),
    ("AGT_04", {"capitalism": 0.6,  "survivalism": 0.1,  "sustainability": 0.4},  {"trust_gain": 1.2},
     "Priya, a restless entrepreneur who treats the market like a game board. She'll gamble on a big crop and isn't afraid to lose, but she's started to care about not wrecking the land."),
    ("AGT_05", {"capitalism": -0.2, "survivalism": 0.5,  "sustainability": 0.6},  {"wariness": 0.7},
     "Sam, a quiet farmer who keeps to the middle of the road. Mildly green, mildly social, he avoids extremes and just wants a steady, decent life."),
    ("AGT_06", {"capitalism": 0.9,  "survivalism": 0.2,  "sustainability": -0.7}, {"wariness": 1.3},
     "Vincent, a sharp-elbowed merchant who measures his worth in gold. He'll squeeze a desperate buyer without blinking and considers sustainability a luxury for people who can't count."),
    ("AGT_07", {"capitalism": -0.8, "survivalism": 0.4,  "sustainability": 0.8},  {"trust_gain": 1.6},
     "Maria, a former relief worker who gives more than she takes. She'll sell at a loss to help a neighbor and believes a community that shares survives together."),
    ("AGT_08", {"capitalism": 0.1,  "survivalism": 0.95, "sustainability": -0.2}, {"wariness": 1.6, "ally_threshold": 0.5},
     "Grigor, a deeply suspicious hoarder who assumes everyone is out to cheat him. He stockpiles obsessively and only deals when cornered."),
    ("AGT_09", {"capitalism": 0.5,  "survivalism": -0.6, "sustainability": -0.3}, {"trust_gain": 1.3},
     "Dice, a thrill-seeker who lives hand-to-mouth by choice. He bets everything on long-shot harvests and laughs off near-starvation."),
    ("AGT_10", {"capitalism": -0.3, "survivalism": 0.3,  "sustainability": 0.95}, {"gossip_susceptibility": 1.4},
     "Aria, a devoted environmentalist who treats water and soil as sacred. She refuses to over-draw resources even when it costs her."),
    ("AGT_11", {"capitalism": 0.0,  "survivalism": 0.5,  "sustainability": 0.0},  {},
     "Nils, a level-headed pragmatist with no ideology to speak of. He reads the market and does the sensible thing."),
    ("AGT_12", {"capitalism": 0.7,  "survivalism": 0.2,  "sustainability": 0.6},  {"trust_gain": 1.1},
     "Eleanor, an ambitious 'green capitalist' convinced you can get rich and do right. She chases profit but won't strip the land bare."),
    ("AGT_13", {"capitalism": -0.6, "survivalism": -0.3, "sustainability": 0.4},  {"trust_gain": 1.3},
     "Cole, an idealistic gambler who hates the profit motive but loves a daring play. He takes wild risks for the collective good."),
    ("AGT_14", {"capitalism": 0.4,  "survivalism": 0.8,  "sustainability": -0.8}, {"wariness": 1.5},
     "Brand, a hard survivalist who'll do whatever it takes to outlast everyone, including bleeding the land dry."),
    ("AGT_15", {"capitalism": -0.9, "survivalism": 0.5,  "sustainability": 0.7},  {"trust_gain": 1.8, "ally_threshold": 0.2},
     "Sunny, a warm-hearted collectivist who trusts almost instantly and believes the group is stronger than the individual."),
    ("AGT_16", {"capitalism": 0.5,  "survivalism": 0.4,  "sustainability": -0.1}, {},
     "Dale, a middle-of-the-road businessman with a modest profit streak, mostly trying to stay in the black."),
    ("AGT_17", {"capitalism": -0.1, "survivalism": 0.7,  "sustainability": 0.6},  {"wariness": 1.2},
     "Iris, a careful steward who balances caution with conscience. She keeps a buffer and prefers sustainable choices."),
    ("AGT_18", {"capitalism": 0.6,  "survivalism": -0.2, "sustainability": -0.4}, {"gossip_susceptibility": 1.5},
     "Rex, a smooth opportunist who follows the money and the mood of the room, quick to switch allegiances."),
    ("AGT_19", {"capitalism": 0.1,  "survivalism": 0.6,  "sustainability": 0.2},  {},
     "Tomas, a stoic moderate who says little and plans steadily, weathering storms by not overreacting."),
    ("AGT_20", {"capitalism": 0.8,  "survivalism": -0.4, "sustainability": -0.9}, {"trust_gain": 0.6, "wariness": 1.4},
     "Sloan, a cold opportunist who exploits weakness wherever it's found and burns resources without a second thought."),
]


def make_population():
    agents = {}
    for aid, ideo, pers, desc in POP:
        a = new_agent(aid, ideo)
        a["memory"] = new_memory(pers)
        a["description"] = desc
        a["dissonance"] = 0.0
        agents[aid] = a
    return agents


def apply_production(agent, prod):
    act = prod["action"]
    if act == "plant" and prod["crop"]:
        plant(agent, prod["crop"])
    elif act == "invest" and agent["plots"]:
        invest(agent, 0, prod["water"], prod["labor"])
    elif act == "expand_water":
        expand_water_cap(agent)


def detect_context(agent, decision, market_prices):
    ctx = {"market_prices": market_prices}
    prod = decision.get("production", {})
    mkt = decision.get("market", {})
    if prod.get("action") == "invest":
        ctx["over_drew_water"] = prod.get("water", 0) > WATER_REGEN_RANGE[1]
        ctx["conserved"] = prod.get("water", 0) == 0
    else:
        ctx["conserved"] = True
    if mkt.get("action") == "post_order" and mkt.get("side") == "ask" and mkt.get("price"):
        ref = market_prices.get(mkt.get("good"))
        if ref and mkt["price"] < ref * 0.85:
            ctx["gave_or_underpriced"] = True
        if ref and mkt["price"] > ref * 1.15:
            ctx["gouged_desperate"] = True
    selling_food = mkt.get("side") == "ask" and mkt.get("good") in ("wheat", "rice", "corn", "kernels")
    if total_food(agent) > 8 * FOOD_PER_CYCLE and not selling_food:
        ctx["hoarded"] = True
    if total_food(agent) < 2 * FOOD_PER_CYCLE and prod.get("action") not in ("plant", "invest"):
        ctx["ran_food_low_voluntarily"] = True
    ctx["low_on_food"] = total_food(agent) < 3 * FOOD_PER_CYCLE
    return ctx


def run(cycles=30, seed=7, verbose=True):
    rng = random.Random(seed)
    agents = make_population()
    book = Ledger()
    unit = ProcessingUnit()
    land = LandRegistry()
    bank = Bank(land)
    clog = CycleLogger("cycle_log.csv")

    for cycle in range(1, cycles + 1):
        market_prices = {g: book.market_price(g) for g in TRADABLE_GOODS}
        corn_mkt = market_prices["corn"]
        unit.reset_cycle()
        bank.reset_cycle()
        kernel_mkt = market_prices["kernels"]
        unit_line = unit.status_line(corn_mkt, kernel_mkt)
        bank_line = bank.status_line()
        if verbose:
            mkt = " | ".join(f"{g} {round(market_prices[g], 2)}" for g in TRADABLE_GOODS)
            print(f"\n===== CYCLE {cycle} | MARKET: {mkt} =====")

        logs = {aid: new_log() for aid, a in agents.items() if a["alive"]}

        for a in agents.values():
            if not a["alive"]:
                continue
            refresh_inputs(a, rng)
            inventory_upkeep(a, logs[a["id"]])
            spoilage(a, logs[a["id"]])

        decisions = {}
        for a in agents.values():
            if not a["alive"]:
                continue
            d = decide(a, market_prices, unit_line, bank_line)
            decisions[a["id"]] = d

            ctx = detect_context(a, d, market_prices)
            av = action_to_vector(a, d, ctx)
            D, dd = dissonance_step(a, av)
            fired = rationalise(a, cycle)
            if fired:
                just, before, after = fired
                remember_event(a, cycle, just, kind="rationalise")
                if verbose:
                    deltas = ", ".join(f"{k} {round(before[k],2)}->{round(after[k],2)}"
                                       for k in ("capitalism", "survivalism", "sustainability")
                                       if abs(after[k]-before[k]) > 0.001)
                    print(f"    ~~ {a['id']} RATIONALISED: {deltas}")

            apply_production(a, d["production"])

            fac = d.get("facility", {})
            if fac.get("action") == "sell_to_unit":
                unit.sell_to_unit(a, fac.get("quantity", 0), corn_mkt)
            elif fac.get("action") == "process":
                unit.process(a, fac.get("quantity", 0), corn_mkt)
            elif fac.get("action") == "buy_from_unit":
                unit.buy_from_unit(a, fac.get("quantity", 0), kernel_mkt)

            bk = d.get("bank", {})
            if bk.get("action") == "buy_plot":
                land.buy_plot(a)
            elif bk.get("action") == "deposit":
                bank.deposit(a, bk.get("amount", 0))
            elif bk.get("action") == "withdraw":
                bank.withdraw(a, bk.get("amount", 0))
            elif bk.get("action") == "borrow":
                bank.borrow(a, bk.get("amount", 0), bk.get("use_collateral", False))
            elif bk.get("action") == "repay":
                bank.repay(a, bk.get("amount", 0))

            m = d["market"]
            if m["action"] == "post_order":
                if not (m["side"] == "ask" and supply_available(a, m["good"]) <= 0):
                    book.post_order(a["id"], m["side"], m["good"],
                                    m["price"], m["quantity"], cycle, m["allow_partial"])
            if verbose:
                p = d["production"]
                mtxt = (f"{m['side']} {m['quantity']} {m['good']}@{m['price']}"
                        if m["action"] == "post_order" else "no order")
                ftxt = f" | UNIT:{fac['action']}({fac.get('quantity')})" if fac.get("action") not in (None, "none") else ""
                print(f"  {a['id']} [g{round(a['gold'],1)} f{total_food(a)} ΔD{round(dd,2)}]: "
                      f"prod={p['action']}({p['crop'] or ''}) | {mtxt}{ftxt} | \"{d['justification']}\"")

        for a in agents.values():
            if a["alive"]:
                plot_upkeep(a, logs[a["id"]])

        trades = book.match_and_settle(agents, cycle, negotiate_fn=llm_negotiate)
        for t in trades:
            buyer, seller = agents[t["buyer"]], agents[t["seller"]]
            st_b = decisions.get(buyer["id"], {}).get("stakes", 0.5)
            st_s = decisions.get(seller["id"], {}).get("stakes", 0.5)
            mp = book.market_price(t["good"]) or t["price"]
            fair_b = (mp - t["price"]) / mp if mp else 0
            fair_s = (t["price"] - mp) / mp if mp else 0
            ensure_relationship(buyer, seller["id"], seller["ideology"])
            ensure_relationship(seller, buyer["id"], buyer["ideology"])
            update_relationship(buyer, seller["id"], seller["ideology"], "trade_success", st_b, fair_b)
            update_relationship(seller, buyer["id"], buyer["ideology"], "trade_success", st_s, fair_s)
            remember_trade_price(buyer, t["good"], t["price"])
            remember_trade_price(seller, t["good"], t["price"])
            remember_event(buyer, cycle, f"bought {t['qty']} {t['good']} @{t['price']}")
            remember_event(seller, cycle, f"sold {t['qty']} {t['good']} @{t['price']}")
            if verbose:
                print(f"    TRADE: {t['buyer']} buys {t['qty']} {t['good']} from {t['seller']} @{t['price']}")

        for f in book.last_failures:
            buyer, seller = agents.get(f["buyer"]), agents.get(f["seller"])
            if not buyer or not seller:
                continue
            ensure_relationship(buyer, seller["id"], seller["ideology"])
            ensure_relationship(seller, buyer["id"], buyer["ideology"])
            update_relationship(buyer, seller["id"], seller["ideology"], "negotiation_failed")
            update_relationship(seller, buyer["id"], buyer["ideology"], "negotiation_failed")
            remember_event(buyer, cycle, f"tried to BUY {f['good']} at {f['bid_price']} — NO DEAL (too low?)", kind="fail")
            remember_event(seller, cycle, f"tried to SELL {f['good']} at {f['ask_price']} — NO DEAL (too high?)", kind="fail")

        for a in agents.values():
            if not a["alive"]:
                continue
            harvested = advance_growth(a, rng, logs[a["id"]])
            for crop, amt in harvested:
                remember_event(a, cycle, f"harvested {amt} {crop}")
            consume(a, logs[a["id"]])
            if not a["alive"]:
                remember_event(a, cycle, "DIED of starvation")
                if verbose:
                    print(f"    {a['id']} DIED of starvation")

        for a in agents.values():
            if a["alive"]:
                decay_relationships(a)
        unit.spoil()
        bank.accrue(agents, market_prices, cycle)
        price_report = book.update_prices_from_pressure()
        clog.log_cycle(cycle, agents, book, unit, bank, land)

        for o in book.expire_orders(cycle):
            owner = agents.get(o["agent_id"])
            if owner and owner["alive"]:
                side = "SELL" if o["side"] == "ask" else "BUY"
                hint = "too high?" if o["side"] == "ask" else "too low?"
                remember_event(owner, cycle,
                               f"my {side} order: {o['quantity']} {o['good']} at {o['price']} went UNFILLED ({hint})",
                               kind="fail")

        if verbose:
            for aid, lg in logs.items():
                a = agents[aid]
                if not a["alive"]:
                    continue
                extra = []
                if lg["spoiled"]:             extra.append(f"spoiled {lg['spoiled']}")
                if lg["plots_died"]:          extra.append(f"plotsDied {lg['plots_died']}")
                if lg["harvest_underyields"]: extra.append(f"underyield {lg['harvest_underyields']}")
                if extra:
                    print(f"    · {aid}: " + ", ".join(extra))
            print(f"    $ UNIT: net money +{round(unit.c_injected-unit.c_absorbed,2)} "
                  f"(injected {round(unit.c_injected,2)}, absorbed {round(unit.c_absorbed,2)}) "
                  f"| govt processing {round(unit.c_processing,2)} | stock {unit.kernels} kernels")
            print(f"    $ BANK: loaned {round(bank.c_loaned,1)} | interest collected {round(bank.c_interest_collected,2)} (SINK) "
                  f"| deposit interest {round(bank.c_deposit_interest,2)} (faucet) "
                  f"| land {land.available()} free @ {land.price()}g | bank-owned {land.bank_owned}")
            money_supply = sum(a["gold"] + a.get("deposit", 0) for a in agents.values() if a["alive"])
            print(f"    $$ MONEY SUPPLY (all agent gold+deposits): {round(money_supply,1)}")
            moves = []
            for g, r in price_report.items():
                arrow = "^" if r["new"] > r["old"] else ("v" if r["new"] < r["old"] else "=")
                if r["new"] != r["old"]:
                    moves.append(f"{g} {r['old']}{arrow}{r['new']}(P{r['pressure']:+})")
            if moves:
                print("    ~ PRICE MOVES: " + " | ".join(moves))

    clog.close()
    print(f"\n[logger] wrote per-cycle data to {clog.path}")
    print("\n========== FINAL STATE ==========")
    for a in agents.values():
        status = "ALIVE" if a["alive"] else "dead"
        i = a["ideology"]
        print(f"  {a['id']}: {status} | gold {round(a['gold'],2)} | food {round(total_food(a))} "
              f"| ΔD {round(a.get('dissonance',0),2)} "
              f"| ideology cap{round(i['capitalism'],2)}/sur{round(i['survivalism'],2)}/sus{round(i['sustainability'],2)}")
    print("\n========== PROCESSING UNIT TOTALS ==========")
    print(f"  gold injected to economy:   {round(unit.gold_injected,2)}")
    print(f"  gold absorbed from economy: {round(unit.gold_absorbed,2)}")
    print(f"  NET money created:          {round(unit.gold_injected-unit.gold_absorbed,2)}")
    print(f"  govt gold spent processing: {round(unit.gold_processing,2)} | labor: {round(unit.labor_used,2)}")
    print(f"  kernels remaining in unit:  {unit.kernels}")
    print("\n========== BANK TOTALS ==========")
    print(f"  gold loaned out:           {round(bank.gold_loaned,2)}")
    print(f"  loan interest collected (sink): {round(bank.interest_collected,2)}")
    print(f"  deposit interest paid (faucet): {round(bank.deposit_interest_paid,2)}")
    print(f"  foreclosures:              {bank.foreclosures}")
    print(f"  land: agent-owned {land.agent_owned}, bank-owned {land.bank_owned}, free {land.available()}")
    return agents, book, unit


if __name__ == "__main__":
    run(cycles=30)
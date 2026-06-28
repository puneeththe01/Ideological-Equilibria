import random
from concurrent.futures import ThreadPoolExecutor
 
DECISION_WORKERS = 20  # how many agent decision calls run concurrently per cycle
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
from respawn import RespawnManager
from checkpoint import save_checkpoint, load_checkpoint, checkpoint_exists, CHECKPOINT_PATH
 
POP = [
    ("AGT_01", {"capitalism": 0.82, "survivalism": -0.09, "sustainability": -0.73}, {'wariness': 1.3},
     "Marcus, a sharp-elbowed trader who measures worth in gold."),
    ("AGT_02", {"capitalism": -0.61, "survivalism": 0.47, "sustainability": 0.85}, {'trust_gain': 1.8, 'ally_threshold': 0.2},
     "Lena, a former relief worker who gives more than they take."),
    ("AGT_03", {"capitalism": 0.01, "survivalism": 0.72, "sustainability": -0.21}, {},
     "Otto, a cautious stockpiler who fears scarcity."),
    ("AGT_04", {"capitalism": 0.52, "survivalism": -0.41, "sustainability": -0.12}, {'trust_gain': 1.3},
     "Priya, a reckless gambler who laughs off near-ruin."),
    ("AGT_05", {"capitalism": -0.22, "survivalism": 0.18, "sustainability": 0.93}, {'wariness': 1.1},
     "Sam, a devoted environmentalist who treats water as sacred."),
    ("AGT_06", {"capitalism": 0.54, "survivalism": 0.05, "sustainability": 0.78}, {'trust_gain': 1.1},
     "Vincent, an entrepreneur who chases profit but spares the land."),
    ("AGT_07", {"capitalism": -0.12, "survivalism": 0.33, "sustainability": 0.1}, {'wariness': 0.7},
     "Maria, a quiet farmer who keeps to the middle road."),
    ("AGT_08", {"capitalism": -0.46, "survivalism": -0.11, "sustainability": 0.36}, {'trust_gain': 1.3},
     "Grigor, a collectivist who takes wild risks for the common good."),
    ("AGT_09", {"capitalism": 0.47, "survivalism": 0.75, "sustainability": -0.65}, {'wariness': 1.5},
     "Dice, a ruthless survivor for whom loyalty is a luxury."),
    ("AGT_10", {"capitalism": 0.61, "survivalism": -0.28, "sustainability": -0.41}, {'gossip_susceptibility': 1.5},
     "Aria, an angle-player quick to switch allegiances."),
    ("AGT_11", {"capitalism": 0.9, "survivalism": 0.33, "sustainability": -0.67}, {'trust_gain': 0.7, 'wariness': 1.4},
     "Nils, a profiteer who squeezes every deal."),
    ("AGT_12", {"capitalism": -0.83, "survivalism": 0.34, "sustainability": 0.74}, {'trust_gain': 1.6},
     "Eleanor, an elder who believes the harvest belongs to all."),
    ("AGT_13", {"capitalism": 0.18, "survivalism": 0.74, "sustainability": -0.01}, {'wariness': 1.6, 'ally_threshold': 0.5},
     "Cole, a famine survivor who trusts numbers over people."),
    ("AGT_14", {"capitalism": 0.45, "survivalism": -0.3, "sustainability": -0.14}, {'trust_gain': 1.3},
     "Brand, a risk-taker who lives hand to mouth by choice."),
    ("AGT_15", {"capitalism": -0.13, "survivalism": 0.35, "sustainability": 0.91}, {'gossip_susceptibility': 1.4},
     "Sunny, a devoted environmentalist who treats water as sacred."),
    ("AGT_16", {"capitalism": 0.72, "survivalism": 0.12, "sustainability": 0.43}, {'trust_gain': 1.1},
     "Dale, an entrepreneur who chases profit but spares the land."),
    ("AGT_17", {"capitalism": 0.05, "survivalism": 0.42, "sustainability": 0.12}, {},
     "Iris, a stoic moderate who plans steadily."),
    ("AGT_18", {"capitalism": -0.62, "survivalism": -0.3, "sustainability": 0.37}, {'trust_gain': 1.3},
     "Rex, a collectivist who takes wild risks for the common good."),
    ("AGT_19", {"capitalism": 0.57, "survivalism": 0.62, "sustainability": -0.81}, {'wariness': 1.5},
     "Tomas, a hard survivalist who'll bleed the land dry to outlast all."),
    ("AGT_20", {"capitalism": 0.43, "survivalism": -0.28, "sustainability": -0.46}, {'gossip_susceptibility': 1.5},
     "Sloan, a smooth opportunist who follows the money and the mood."),
    ("AGT_21", {"capitalism": 0.81, "survivalism": 0.09, "sustainability": -0.54}, {'trust_gain': 0.7, 'wariness': 1.4},
     "Hana, a profiteer who squeezes every deal."),
    ("AGT_22", {"capitalism": -0.51, "survivalism": 0.54, "sustainability": 0.41}, {'trust_gain': 1.6},
     "Bjorn, an elder who believes the harvest belongs to all."),
    ("AGT_23", {"capitalism": 0.2, "survivalism": 0.83, "sustainability": -0.19}, {'wariness': 1.6, 'ally_threshold': 0.5},
     "Kwame, a cautious stockpiler who fears scarcity."),
    ("AGT_24", {"capitalism": 0.34, "survivalism": -0.53, "sustainability": -0.22}, {'gossip_susceptibility': 1.4},
     "Yuki, a risk-taker who lives hand to mouth by choice."),
    ("AGT_25", {"capitalism": -0.01, "survivalism": 0.33, "sustainability": 0.84}, {'wariness': 1.1},
     "Ines, a devoted environmentalist who treats water as sacred."),
    ("AGT_26", {"capitalism": 0.74, "survivalism": 0.15, "sustainability": 0.48}, {'trust_gain': 1.1},
     "Pavel, an entrepreneur who chases profit but spares the land."),
    ("AGT_27", {"capitalism": 0.01, "survivalism": 0.53, "sustainability": 0.01}, {'wariness': 0.7},
     "Rosa, a level-headed pragmatist with no ideology to speak of."),
    ("AGT_28", {"capitalism": -0.55, "survivalism": -0.36, "sustainability": 0.31}, {'trust_gain': 1.3},
     "Dimitri, a collectivist who takes wild risks for the common good."),
    ("AGT_29", {"capitalism": 0.32, "survivalism": 0.76, "sustainability": -0.52}, {'wariness': 1.5},
     "Asha, a hard survivalist who'll bleed the land dry to outlast all."),
    ("AGT_30", {"capitalism": 0.64, "survivalism": 0.09, "sustainability": -0.29}, {'gossip_susceptibility': 1.5},
     "Felix, a smooth opportunist who follows the money and the mood."),
    ("AGT_31", {"capitalism": 0.83, "survivalism": 0.37, "sustainability": -0.8}, {'trust_gain': 0.7, 'wariness': 1.4},
     "Noor, a cold dealer who exploits the desperate."),
    ("AGT_32", {"capitalism": -0.51, "survivalism": 0.57, "sustainability": 0.78}, {'trust_gain': 1.6},
     "Greta, an elder who believes the harvest belongs to all."),
    ("AGT_33", {"capitalism": 0.21, "survivalism": 0.8, "sustainability": -0.03}, {'wariness': 1.6, 'ally_threshold': 0.5},
     "Hugo, a paranoid hoarder who only deals when cornered."),
    ("AGT_34", {"capitalism": 0.66, "survivalism": -0.52, "sustainability": -0.3}, {'gossip_susceptibility': 1.4},
     "Mei, a thrill-seeker who bets everything on long shots."),
    ("AGT_35", {"capitalism": -0.39, "survivalism": 0.27, "sustainability": 0.86}, {'gossip_susceptibility': 1.4},
     "Tariq, a devoted environmentalist who treats water as sacred."),
    ("AGT_36", {"capitalism": 0.68, "survivalism": 0.02, "sustainability": 0.43}, {},
     "Lucia, an ambitious green capitalist sure you can profit and do right."),
    ("AGT_37", {"capitalism": -0.13, "survivalism": 0.37, "sustainability": 0.05}, {},
     "Sven, a level-headed pragmatist with no ideology to speak of."),
    ("AGT_38", {"capitalism": -0.48, "survivalism": -0.05, "sustainability": 0.37}, {'trust_gain': 1.3},
     "Zara, an idealistic gambler who hates profit but loves a daring play."),
    ("AGT_39", {"capitalism": 0.54, "survivalism": 0.56, "sustainability": -0.86}, {'wariness': 1.5},
     "Owen, a ruthless survivor for whom loyalty is a luxury."),
    ("AGT_40", {"capitalism": 0.53, "survivalism": -0.11, "sustainability": -0.21}, {'gossip_susceptibility': 1.5},
     "Petra, a smooth opportunist who follows the money and the mood."),
    ("AGT_41", {"capitalism": 0.74, "survivalism": 0.07, "sustainability": -0.38}, {'wariness': 1.3},
     "Ravi, a sharp-elbowed trader who measures worth in gold."),
    ("AGT_42", {"capitalism": -0.82, "survivalism": 0.38, "sustainability": 0.61}, {'trust_gain': 1.8, 'ally_threshold': 0.2},
     "Klara, a communitarian who shares in lean times."),
    ("AGT_43", {"capitalism": 0.07, "survivalism": 0.93, "sustainability": -0.12}, {},
     "Mateo, a cautious stockpiler who fears scarcity."),
    ("AGT_44", {"capitalism": 0.32, "survivalism": -0.3, "sustainability": -0.07}, {'trust_gain': 1.3},
     "Saoirse, a thrill-seeker who bets everything on long shots."),
    ("AGT_45", {"capitalism": -0.33, "survivalism": 0.25, "sustainability": 0.76}, {'gossip_susceptibility': 1.4},
     "Anton, a green idealist who won't over-draw resources."),
    ("AGT_46", {"capitalism": 0.47, "survivalism": 0.0, "sustainability": 0.56}, {},
     "Delia, an entrepreneur who chases profit but spares the land."),
    ("AGT_47", {"capitalism": -0.02, "survivalism": 0.59, "sustainability": 0.15}, {'wariness': 0.7},
     "Omar, a quiet farmer who keeps to the middle road."),
    ("AGT_48", {"capitalism": -0.65, "survivalism": -0.28, "sustainability": 0.49}, {'trust_gain': 1.3},
     "Freya, an idealistic gambler who hates profit but loves a daring play."),
    ("AGT_49", {"capitalism": 0.32, "survivalism": 0.68, "sustainability": -0.7}, {'wariness': 1.5},
     "Cyrus, a hard survivalist who'll bleed the land dry to outlast all."),
    ("AGT_50", {"capitalism": 0.69, "survivalism": -0.27, "sustainability": -0.43}, {'gossip_susceptibility': 1.5},
     "Mabel, a smooth opportunist who follows the money and the mood."),
    ("AGT_51", {"capitalism": 0.74, "survivalism": 0.37, "sustainability": -0.56}, {'wariness': 1.3},
     "Jonas, a cold dealer who exploits the desperate."),
    ("AGT_52", {"capitalism": -0.65, "survivalism": 0.37, "sustainability": 0.69}, {'trust_gain': 1.8, 'ally_threshold': 0.2},
     "Esme, an elder who believes the harvest belongs to all."),
    ("AGT_53", {"capitalism": 0.28, "survivalism": 0.75, "sustainability": -0.01}, {'wariness': 1.6, 'ally_threshold': 0.5},
     "Viktor, a famine survivor who trusts numbers over people."),
    ("AGT_54", {"capitalism": 0.46, "survivalism": -0.43, "sustainability": -0.28}, {'trust_gain': 1.3},
     "Talia, a reckless gambler who laughs off near-ruin."),
    ("AGT_55", {"capitalism": -0.4, "survivalism": 0.29, "sustainability": 0.85}, {'gossip_susceptibility': 1.4},
     "Rafael, a devoted environmentalist who treats water as sacred."),
    ("AGT_56", {"capitalism": 0.62, "survivalism": 0.15, "sustainability": 0.45}, {'trust_gain': 1.1},
     "Oona, an entrepreneur who chases profit but spares the land."),
    ("AGT_57", {"capitalism": 0.11, "survivalism": 0.41, "sustainability": -0.1}, {'wariness': 0.7},
     "Lars, a quiet farmer who keeps to the middle road."),
    ("AGT_58", {"capitalism": -0.52, "survivalism": -0.01, "sustainability": 0.4}, {'trust_gain': 1.3},
     "Indira, an idealistic gambler who hates profit but loves a daring play."),
    ("AGT_59", {"capitalism": 0.58, "survivalism": 0.53, "sustainability": -0.55}, {'wariness': 1.5},
     "Cato, a ruthless survivor for whom loyalty is a luxury."),
    ("AGT_60", {"capitalism": 0.67, "survivalism": -0.0, "sustainability": -0.44}, {'gossip_susceptibility': 1.5},
     "Bex, an angle-player quick to switch allegiances."),
    ("AGT_61", {"capitalism": 0.85, "survivalism": 0.0, "sustainability": -0.52}, {'trust_gain': 0.7, 'wariness': 1.4},
     "Magnus, a profiteer who squeezes every deal."),
    ("AGT_62", {"capitalism": -0.8, "survivalism": 0.56, "sustainability": 0.43}, {'trust_gain': 1.8, 'ally_threshold': 0.2},
     "Soraya, an elder who believes the harvest belongs to all."),
    ("AGT_63", {"capitalism": 0.25, "survivalism": 0.71, "sustainability": -0.17}, {'wariness': 1.6, 'ally_threshold': 0.5},
     "Emil, a famine survivor who trusts numbers over people."),
    ("AGT_64", {"capitalism": 0.36, "survivalism": -0.52, "sustainability": -0.12}, {'trust_gain': 1.3},
     "Carmen, a risk-taker who lives hand to mouth by choice."),
    ("AGT_65", {"capitalism": -0.36, "survivalism": 0.38, "sustainability": 0.89}, {'gossip_susceptibility': 1.4},
     "Yusuf, a devoted environmentalist who treats water as sacred."),
    ("AGT_66", {"capitalism": 0.73, "survivalism": 0.17, "sustainability": 0.46}, {'trust_gain': 1.1},
     "Dagny, an ambitious green capitalist sure you can profit and do right."),
    ("AGT_67", {"capitalism": -0.06, "survivalism": 0.57, "sustainability": 0.09}, {'wariness': 0.7},
     "Pablo, a level-headed pragmatist with no ideology to speak of."),
    ("AGT_68", {"capitalism": -0.64, "survivalism": -0.3, "sustainability": 0.23}, {'trust_gain': 1.3},
     "Linnea, a collectivist who takes wild risks for the common good."),
    ("AGT_69", {"capitalism": 0.58, "survivalism": 0.57, "sustainability": -0.83}, {'wariness': 1.5},
     "Idris, a hard survivalist who'll bleed the land dry to outlast all."),
    ("AGT_70", {"capitalism": 0.41, "survivalism": -0.01, "sustainability": -0.37}, {'gossip_susceptibility': 1.5},
     "Wren, an angle-player quick to switch allegiances."),
    ("AGT_71", {"capitalism": 0.69, "survivalism": 0.29, "sustainability": -0.84}, {'trust_gain': 0.7, 'wariness': 1.4},
     "Goran, a sharp-elbowed trader who measures worth in gold."),
    ("AGT_72", {"capitalism": -0.81, "survivalism": 0.53, "sustainability": 0.63}, {'trust_gain': 1.6},
     "Suri, a communitarian who shares in lean times."),
    ("AGT_73", {"capitalism": 0.07, "survivalism": 0.87, "sustainability": -0.14}, {},
     "Bram, a paranoid hoarder who only deals when cornered."),
    ("AGT_74", {"capitalism": 0.69, "survivalism": -0.59, "sustainability": -0.14}, {'gossip_susceptibility': 1.4},
     "Calla, a reckless gambler who laughs off near-ruin."),
    ("AGT_75", {"capitalism": -0.02, "survivalism": 0.13, "sustainability": 0.96}, {'wariness': 1.1},
     "Dragan, a devoted environmentalist who treats water as sacred."),
    ("AGT_76", {"capitalism": 0.42, "survivalism": 0.18, "sustainability": 0.54}, {},
     "Neve, an entrepreneur who chases profit but spares the land."),
    ("AGT_77", {"capitalism": 0.03, "survivalism": 0.45, "sustainability": -0.03}, {},
     "Hassan, a quiet farmer who keeps to the middle road."),
    ("AGT_78", {"capitalism": -0.62, "survivalism": -0.12, "sustainability": 0.2}, {'trust_gain': 1.3},
     "Verity, an idealistic gambler who hates profit but loves a daring play."),
    ("AGT_79", {"capitalism": 0.43, "survivalism": 0.78, "sustainability": -0.53}, {'wariness': 1.5},
     "Lev, a ruthless survivor for whom loyalty is a luxury."),
    ("AGT_80", {"capitalism": 0.62, "survivalism": -0.18, "sustainability": -0.38}, {'gossip_susceptibility': 1.5},
     "Mira, an angle-player quick to switch allegiances."),
    ("AGT_81", {"capitalism": 0.74, "survivalism": 0.05, "sustainability": -0.82}, {'trust_gain': 0.7, 'wariness': 1.4},
     "Quinn, a profiteer who squeezes every deal."),
    ("AGT_82", {"capitalism": -0.63, "survivalism": 0.56, "sustainability": 0.71}, {'trust_gain': 1.8, 'ally_threshold': 0.2},
     "Adela, a communitarian who shares in lean times."),
    ("AGT_83", {"capitalism": 0.16, "survivalism": 0.7, "sustainability": -0.19}, {'wariness': 1.6, 'ally_threshold': 0.5},
     "Boris, a paranoid hoarder who only deals when cornered."),
    ("AGT_84", {"capitalism": 0.49, "survivalism": -0.52, "sustainability": -0.31}, {'trust_gain': 1.3},
     "Tindra, a reckless gambler who laughs off near-ruin."),
    ("AGT_85", {"capitalism": -0.14, "survivalism": 0.19, "sustainability": 0.88}, {'wariness': 1.1},
     "Samir, a steward who conserves even at personal cost."),
    ("AGT_86", {"capitalism": 0.44, "survivalism": 0.29, "sustainability": 0.49}, {'trust_gain': 1.1},
     "Orla, an entrepreneur who chases profit but spares the land."),
    ("AGT_87", {"capitalism": 0.09, "survivalism": 0.34, "sustainability": -0.14}, {},
     "Stefan, a stoic moderate who plans steadily."),
    ("AGT_88", {"capitalism": -0.56, "survivalism": -0.05, "sustainability": 0.37}, {'trust_gain': 1.3},
     "Maeve, a collectivist who takes wild risks for the common good."),
    ("AGT_89", {"capitalism": 0.42, "survivalism": 0.54, "sustainability": -0.62}, {'wariness': 1.5},
     "Cassius, a hard survivalist who'll bleed the land dry to outlast all."),
    ("AGT_90", {"capitalism": 0.47, "survivalism": 0.02, "sustainability": -0.22}, {'gossip_susceptibility': 1.5},
     "Liv, an angle-player quick to switch allegiances."),
    ("AGT_91", {"capitalism": 0.8, "survivalism": 0.36, "sustainability": -0.83}, {'trust_gain': 0.7, 'wariness': 1.4},
     "Renzo, a sharp-elbowed trader who measures worth in gold."),
    ("AGT_92", {"capitalism": -0.63, "survivalism": 0.6, "sustainability": 0.7}, {'trust_gain': 1.8, 'ally_threshold': 0.2},
     "Saga, a communitarian who shares in lean times."),
    ("AGT_93", {"capitalism": 0.25, "survivalism": 0.84, "sustainability": 0.06}, {'wariness': 1.6, 'ally_threshold': 0.5},
     "Dario, a cautious stockpiler who fears scarcity."),
    ("AGT_94", {"capitalism": 0.48, "survivalism": -0.4, "sustainability": -0.06}, {'gossip_susceptibility': 1.4},
     "Fenna, a reckless gambler who laughs off near-ruin."),
    ("AGT_95", {"capitalism": -0.15, "survivalism": 0.18, "sustainability": 0.72}, {'gossip_susceptibility': 1.4},
     "Milo, a green idealist who won't over-draw resources."),
    ("AGT_96", {"capitalism": 0.51, "survivalism": 0.1, "sustainability": 0.62}, {'trust_gain': 1.1},
     "Astra, an ambitious green capitalist sure you can profit and do right."),
    ("AGT_97", {"capitalism": -0.08, "survivalism": 0.51, "sustainability": 0.06}, {'wariness': 0.7},
     "Roni, a level-headed pragmatist with no ideology to speak of."),
    ("AGT_98", {"capitalism": -0.58, "survivalism": -0.18, "sustainability": 0.32}, {'trust_gain': 1.3},
     "Despina, an idealistic gambler who hates profit but loves a daring play."),
    ("AGT_99", {"capitalism": 0.42, "survivalism": 0.73, "sustainability": -0.52}, {'wariness': 1.5},
     "Caleb, a hard survivalist who'll bleed the land dry to outlast all."),
    ("AGT_100", {"capitalism": 0.54, "survivalism": 0.08, "sustainability": -0.38}, {'gossip_susceptibility': 1.5},
     "Vesna, an angle-player quick to switch allegiances."),
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
 
 
def run(cycles=30, seed=7, verbose=True, checkpoint_every=25):
    rng = random.Random(seed)
    ckpt = load_checkpoint()
    if ckpt:
        start_cycle = ckpt["cycle"] + 1
        rng.setstate(ckpt["rng"])
        agents = ckpt["agents"]
        book = ckpt["book"]
        unit = ckpt["unit"]
        land = ckpt["land"]
        bank = ckpt["bank"]
        respawner = ckpt["respawner"]
        CycleLogger.trim_from("cycle_log.csv", start_cycle)
        clog = CycleLogger("cycle_log.csv", append=True)
        print(f"[checkpoint] resuming from cycle {start_cycle} (loaded state at cycle {ckpt['cycle']})")
    else:
        start_cycle = 1
        agents = make_population()
        book = Ledger()
        unit = ProcessingUnit()
        land = LandRegistry()
        bank = Bank(land)
        clog = CycleLogger("cycle_log.csv")
        respawner = RespawnManager(rng=rng, next_id=101)
 
    for cycle in range(start_cycle, cycles + 1):
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
 
        # ---- PHASE 1: gather all agent decisions IN PARALLEL (the slow LLM calls) ----
        living = [a for a in agents.values() if a["alive"]]
 
        def _get_decision(a):
            try:
                return a["id"], decide(a, market_prices, unit_line, bank_line)
            except Exception as e:
                print(f"    [{a['id']}] decide failed: {e}")
                return a["id"], None
 
        decisions = {}
        with ThreadPoolExecutor(max_workers=DECISION_WORKERS) as pool:
            for aid, d in pool.map(_get_decision, living):
                decisions[aid] = d
 
        # ---- PHASE 2: apply decisions SEQUENTIALLY (keeps the economy deterministic) ----
        for a in living:
            d = decisions.get(a["id"])
            if d is None:
                continue
 
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
            st_b = (decisions.get(buyer["id"]) or {}).get("stakes", 0.5)
            st_s = (decisions.get(seller["id"]) or {}).get("stakes", 0.5)
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
 
        _dead_this_cycle = []
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
                _dead_this_cycle.append(a)
 
        for dead in _dead_this_cycle:
            living = [x for x in agents.values() if x["alive"]]
            newborn = respawner.spawn(dead, living, cycle)
            agents[newborn["id"]] = newborn
            logs[newborn["id"]] = new_log()
            if verbose:
                print(f"    + {newborn['id']} born (replacing {dead['id']})")
 
        for a in agents.values():
            if a["alive"]:
                decay_relationships(a)
        unit.spoil()
        bank.accrue(agents, market_prices, cycle)
        price_report = book.update_prices_from_pressure()
        clog.log_cycle(cycle, agents, book, unit, bank, land)
        if cycle % checkpoint_every == 0:
            save_checkpoint(cycle, rng, agents, book, unit, land, bank, respawner)
            if verbose:
                print(f"    [checkpoint] saved at cycle {cycle}")
 
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
    import os as _os
    if checkpoint_exists():
        _os.remove(CHECKPOINT_PATH)
        print("[checkpoint] run complete — checkpoint cleared")
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
    print("\n========== RESPAWN TOTALS ==========")
    print(f"  agents born:                {respawner.births}")
    print(f"  gold injected by newborns:  {round(respawner.gold_injected,2)}")
    print(f"  final population size:      {sum(1 for a in agents.values() if a['alive'])} alive / {len(agents)} total")
    return agents, book, unit
 
 
if __name__ == "__main__":
    run(cycles=1000)

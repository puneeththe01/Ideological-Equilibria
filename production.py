import random
from config import (
    KERNEL_SPOIL, KERNEL_FOOD_VALUE,
    FOOD_PER_CYCLE, DEATH_STARVATION, STARTING_GOLD, STARTING_WATER, STARTING_FOOD,
    LABOR_REFRESH_RANGE, LABOR_CAP, WATER_REGEN_RANGE, WATER_CAP_INITIAL,
    WATER_CAP_EXPANSION, WATER_CAP_EXPANSION_COST, CROPS,
    INV_UPKEEP_THRESHOLD, SPOIL_RAMP_PER_CYCLE,
    PLOT_UPKEEP_LABOR, PLOT_UPKEEP_GOLD, PLOT_HEALTH_START, PLOT_HEALTH_DECAY,
    PLOT_SCAR_THRESHOLD, PLOT_SCAR_PENALTY, DEAD_PLOT_CLEAR_GOLD,
)

CROP_KEYS = ("wheat", "rice", "corn")        
FOOD_KEYS = ("wheat", "rice", "corn", "kernels")  

EAT_ORDER = ("corn", "wheat", "rice", "kernels")
FOOD_VALUE = {"wheat": 1.0, "rice": 1.0, "corn": 1.0, "kernels": KERNEL_FOOD_VALUE}


def new_agent(agent_id, ideology, gold=None):
    return {
        "id": agent_id,
        "ideology": ideology,
        "gold": STARTING_GOLD if gold is None else gold,
        "inventory": {**dict(STARTING_FOOD), "kernels": 0},
        "labor": 0,                       
        "water": STARTING_WATER,
        "water_cap": WATER_CAP_INITIAL,
        "plots": [],                     
        "owned_plots": [],               
        "loan": None,                   
        "deposit": 0.0,                  
        "starvation": 0,
        "labor_debt_cycles": 0,           
        "spoil_penalty": 0.0,            
        "alive": True,
    }


def total_food(agent):
    return sum(agent["inventory"].get(c, 0) * FOOD_VALUE[c] for c in FOOD_KEYS)

def new_log():
    return {k: 0 for k in (
        "eaten", "spoiled", "upkeep_inv_labor", "upkeep_unpaid",
        "upkeep_plot_labor", "upkeep_plot_gold", "plots_died",
        "harvest_underyields", "harvest_failures",
    )}

def refresh_inputs(agent, rng):
    """Labor accumulates up to LABOR_CAP; water regenerates up to its cap."""
    agent["labor"] = min(LABOR_CAP, agent["labor"] + rng.randint(*LABOR_REFRESH_RANGE))
    agent["water"] = min(agent["water"] + rng.randint(*WATER_REGEN_RANGE), agent["water_cap"])


def inventory_upkeep(agent, log):
    """Charge labor to maintain stockpiles. Unpaid -> labor goes negative + spoilage ramps up."""
    cost = sum(agent["inventory"][c] // INV_UPKEEP_THRESHOLD[c] for c in CROP_KEYS)
    if cost <= 0:
        agent["labor_debt_cycles"] = 0
        agent["spoil_penalty"] = max(0.0, agent["spoil_penalty"] - SPOIL_RAMP_PER_CYCLE)
        return
    if agent["labor"] >= cost:
        agent["labor"] -= cost
        agent["labor_debt_cycles"] = 0
        agent["spoil_penalty"] = max(0.0, agent["spoil_penalty"] - SPOIL_RAMP_PER_CYCLE)
        log["upkeep_inv_labor"] += cost
    else:
        paid = max(0, agent["labor"])
        agent["labor"] -= cost                 
        agent["labor_debt_cycles"] += 1
        agent["spoil_penalty"] += SPOIL_RAMP_PER_CYCLE
        log["upkeep_inv_labor"] += paid
        log["upkeep_unpaid"] += (cost - paid)


def spoilage(agent, log):
    """Each food store decays by its own spoil rate plus any ramped penalty."""
    for c in FOOD_KEYS:
        base = KERNEL_SPOIL if c == "kernels" else CROPS[c]["spoil"]
        rate = base + agent["spoil_penalty"]
        lost = int(agent["inventory"].get(c, 0) * rate)
        if lost > 0:
            agent["inventory"][c] -= lost
            log["spoiled"] += lost

def plant(agent, crop):
    if crop not in CROPS:
        return False
    agent["plots"].append({"crop": crop, "water": 0, "labor": 0,
                           "health": PLOT_HEALTH_START, "scarred": False})
    return True


def invest(agent, idx, water_amt, labor_amt):
    if not (0 <= idx < len(agent["plots"])):
        return False
    water_amt = max(0, min(water_amt, agent["water"]))
    labor_amt = max(0, min(labor_amt, max(0, agent["labor"]))) 
    p = agent["plots"][idx]
    p["water"] += water_amt
    p["labor"] += labor_amt
    agent["water"] -= water_amt
    agent["labor"] -= labor_amt
    return True


def expand_water_cap(agent):
    if agent["gold"] >= WATER_CAP_EXPANSION_COST:
        agent["gold"] -= WATER_CAP_EXPANSION_COST
        agent["water_cap"] += WATER_CAP_EXPANSION
        return True
    return False



def plot_upkeep(agent, log):
    """Charge labor+gold per active planting. OWNED land covers the GOLD portion for that
    many plantings (you don't rent land you own); labor upkeep is always charged.
    Unpaid -> health decays; <70 scars; 0 kills it."""
    survivors = []
    owned_cover = len(agent.get("owned_plots", []))  
    for idx, plot in enumerate(agent["plots"]):
        gold_due = 0 if idx < owned_cover else PLOT_UPKEEP_GOLD
        if agent["labor"] >= PLOT_UPKEEP_LABOR and agent["gold"] >= gold_due:
            agent["labor"] -= PLOT_UPKEEP_LABOR
            agent["gold"] -= gold_due
            log["upkeep_plot_labor"] += PLOT_UPKEEP_LABOR
            log["upkeep_plot_gold"] += gold_due
        else:
            plot["health"] -= PLOT_HEALTH_DECAY
            if plot["health"] < PLOT_SCAR_THRESHOLD:
                plot["scarred"] = True
            if plot["health"] <= 0:
                agent["gold"] -= DEAD_PLOT_CLEAR_GOLD
                log["plots_died"] += 1
                log["upkeep_plot_gold"] += DEAD_PLOT_CLEAR_GOLD
                continue  
        survivors.append(plot)
    agent["plots"] = survivors


def advance_growth(agent, rng, log):
    """Harvest any plot whose water AND labor needs are met. Applies harvest risk + scar penalty."""
    harvested, remaining = [], []
    for p in agent["plots"]:
        spec = CROPS[p["crop"]]
        if p["water"] >= spec["req_water"] and p["labor"] >= spec["req_labor"]:
            amount = rng.randint(*spec["yield_range"])
            if rng.random() < spec["harvest_risk"]:
                if rng.random() < 0.05:                 
                    amount = 0
                    log["harvest_failures"] += 1
                else:                                   
                    amount = int(amount * rng.uniform(0.3, 0.7))
                    log["harvest_underyields"] += 1
            if p["scarred"]:
                amount = int(amount * (1 - PLOT_SCAR_PENALTY))
            agent["inventory"][p["crop"]] += amount
            harvested.append((p["crop"], amount))
        else:
            remaining.append(p)
    agent["plots"] = remaining
    return harvested


def _eat_one_point(agent):
    """Consume ~1 food point, drawing the fastest-spoiling store first.
    Returns the food value actually eaten (kernels yield 1.5 per unit)."""
    for c in EAT_ORDER:
        if agent["inventory"].get(c, 0) > 0:
            agent["inventory"][c] -= 1
            return FOOD_VALUE[c]
    return 0.0


def consume(agent, log):
    """Eat FOOD_PER_CYCLE food points; pay down starvation with surplus; die if too starved."""
    need = float(FOOD_PER_CYCLE)
    eaten = 0.0
    while need > 0:
        v = _eat_one_point(agent)
        if v == 0:
            break
        eaten += v
        need -= v
    log["eaten"] += round(eaten)
    if need > 0:
        agent["starvation"] += int(round(need))

    while agent["starvation"] > 0 and total_food(agent) > 0:
        v = _eat_one_point(agent)
        if v == 0:
            break
        agent["starvation"] -= int(round(v)) or 1

    if agent["starvation"] > DEATH_STARVATION:
        agent["alive"] = False



if __name__ == "__main__":
    rng = random.Random(7)
    a = new_agent("AGT", {"capitalism": 0.5, "survivalism": 0.5, "sustainability": 0.0})
    plant(a, "corn")  
    for cycle in range(1, 9):
        log = new_log()
        refresh_inputs(a, rng)
        inventory_upkeep(a, log)
        spoilage(a, log)
        if a["plots"]:
            invest(a, 0, a["water"], a["labor"])
        plot_upkeep(a, log)
        harvested = advance_growth(a, rng, log)
        consume(a, log)
        print(f"C{cycle:2d} | g{a['gold']:3d} f{total_food(a):3d} labor{a['labor']:3d} "
              f"| spoiled{log['spoiled']} ate{log['eaten']} "
              f"{'HARVEST ' + str(harvested) if harvested else ''}")
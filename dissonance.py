from config import DISSONANCE_DECAY, DISSONANCE_THRESHOLD, MUTATION_STEP

AXES = ("capitalism", "survivalism", "sustainability")


def _clamp(x, lo=-1.0, hi=1.0):
    return max(lo, min(hi, x))


def action_to_vector(agent, decision, context):
    """Map this cycle's action to a vector in [-1,1]^3. Deterministic & explainable.
    context carries detected facts: market_prices, over_drew_water, gouged_desperate,
    gave_or_underpriced, hoarded, gave_away_food, ran_food_low_voluntarily, conserved.
    """
    cap = sur = sus = 0.0
    prod = decision.get("production", {})
    mkt = decision.get("market", {})
    bk = decision.get("bank", {})

    if isinstance(bk, dict):
        if bk.get("action") == "borrow":
            sur -= 0.2          
        elif bk.get("action") in ("deposit", "buy_plot"):
            cap += 0.2          

    if mkt.get("action") == "post_order" and mkt.get("price") is not None:
        good = mkt.get("good")
        ref = context["market_prices"].get(good)
        if ref:
            rel = (mkt["price"] - ref) / ref
            if mkt.get("side") == "ask":
                cap += _clamp(rel * 3.0)     
            elif mkt.get("side") == "bid":
                cap += _clamp(-rel * 3.0)       
    if context.get("gouged_desperate"):
        cap += 0.5
    if context.get("gave_or_underpriced"):
        cap -= 0.6

    if prod.get("action") in ("plant", "invest"):
        sur += 0.1                             
    if context.get("hoarded"):
        sur += 0.4
    if context.get("gave_away_food"):
        sur -= 0.7
    if context.get("ran_food_low_voluntarily"):
        sur -= 0.4
    if mkt.get("side") == "ask" and mkt.get("good") in ("wheat", "rice", "corn"):
        sur -= 0.2                             

    fac = decision.get("facility", {})
    if isinstance(fac, dict):
        if fac.get("action") == "sell_to_unit":
            cap += 0.2                        
        elif fac.get("action") == "process":
            sus += 0.2                         
        elif fac.get("action") == "buy_from_unit" and context.get("low_on_food"):
            sur += 0.2                        

    if context.get("over_drew_water"):
        sus -= 0.7
    elif prod.get("action") == "invest" and prod.get("water", 0) > 0:
        sus += 0.2                              
    if prod.get("action") == "expand_water":
        sus += 0.1
    if context.get("conserved"):
        sus += 0.4

    return {"capitalism": _clamp(cap), "survivalism": _clamp(sur), "sustainability": _clamp(sus)}


def dissonance_step(agent, action_vec):
    """D_t = mean squared distance between ideology and action; accumulate with decay gamma."""
    K = len(AXES)
    D = sum((agent["ideology"][k] - action_vec[k]) ** 2 for k in AXES) / (2 * K)
    dd = DISSONANCE_DECAY * agent.get("dissonance", 0.0) + D
    agent["dissonance"] = dd
    agent["last_action_vec"] = action_vec
    return D, dd


def rationalise(agent, cycle):
    """If accumulated ΔD >= theta: mutate ideology toward behaviour, justify, reset ΔD.
    Returns (justification, before_ideology, after_ideology) if it fired, else None."""
    if agent.get("dissonance", 0.0) < DISSONANCE_THRESHOLD:
        return None
    av = agent.get("last_action_vec")
    if not av:
        return None

    before = dict(agent["ideology"])
    for k in AXES:
        agent["ideology"][k] = _clamp(
            agent["ideology"][k] + MUTATION_STEP * (av[k] - agent["ideology"][k])
        )

    moved = max(AXES, key=lambda k: abs(agent["ideology"][k] - before[k]))
    direction = "toward" if agent["ideology"][moved] > before[moved] else "away from"
    justification = (f"My actions kept clashing with my beliefs, so I have made peace with it: "
                     f"I now lean {direction} {moved}. Survival shapes who you become.")

    agent["dissonance"] = 0.0
    return justification, before, dict(agent["ideology"])
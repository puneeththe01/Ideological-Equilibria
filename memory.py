"""
memory.py — the personal memory layer for each agent.

v3 CHANGES vs previous:
  - Failed-deal events are tagged kind="fail" and surfaced as a dedicated line in the
    memory block, so the agent can adjust its pricing next time.
  - Privacy preserved: an agent's block only ever contains ITS OWN activity and the
    relationships IT has formed — never a view of all market trades.
"""

import math
from config import EPISODIC_WINDOW, R_DECAY, AFFINITY_WEIGHT, DEFAULT_PERSONALITY


def cosine_similarity(ideo_a, ideo_b):
    keys = ("capitalism", "survivalism", "sustainability")
    a = [ideo_a[k] for k in keys]
    b = [ideo_b[k] for k in keys]
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def new_memory(personality=None):
    p = dict(DEFAULT_PERSONALITY)
    if personality:
        p.update(personality)
    return {
        "episodic": [],
        "trade_prices": {},
        "relationships": {},
        "personality": p,
    }


# ---------- relationships ----------

def _affinity_baseline(agent, other_ideology):
    return AFFINITY_WEIGHT * cosine_similarity(agent["ideology"], other_ideology)


def ensure_relationship(agent, other_id, other_ideology):
    rels = agent["memory"]["relationships"]
    if other_id not in rels:
        base = _affinity_baseline(agent, other_ideology)
        rels[other_id] = {"R": base, "baseline": base}
    return rels[other_id]


def update_relationship(agent, other_id, other_ideology, event, stakes=0.5, fairness=0.0):
    rel = ensure_relationship(agent, other_id, other_ideology)
    p = agent["memory"]["personality"]
    if event == "trade_success":
        delta = 0.25 * (0.5 + stakes) * (1.0 + fairness) * p["trust_gain"]
    elif event == "negotiation_failed":
        delta = -0.05 * p["wariness"]
    elif event == "refused_while_needed":
        delta = -0.30 * (0.5 + stakes) * p["wariness"]
    else:
        delta = 0.0
    rel["R"] = max(-1.0, min(1.0, rel["R"] + delta))
    return rel["R"]


def decay_relationships(agent):
    for rel in agent["memory"]["relationships"].values():
        rel["R"] = rel["baseline"] + R_DECAY * (rel["R"] - rel["baseline"])


def classify(agent, other_id):
    rel = agent["memory"]["relationships"].get(other_id)
    if not rel:
        return "unknown"
    p = agent["memory"]["personality"]
    if rel["R"] >= p["ally_threshold"]:
        return "ally"
    if rel["R"] <= p["rival_threshold"]:
        return "rival"
    return "neutral"


# ---------- episodic + price memory ----------

def remember_event(agent, cycle, text, kind="action"):
    log = agent["memory"]["episodic"]
    log.append({"cycle": cycle, "text": text, "kind": kind})
    cutoff = cycle - EPISODIC_WINDOW
    agent["memory"]["episodic"] = [e for e in log if e["cycle"] > cutoff]


def remember_trade_price(agent, good, price):
    tp = agent["memory"]["trade_prices"].setdefault(good, [])
    tp.append(price)
    if len(tp) > EPISODIC_WINDOW:
        tp.pop(0)


# ---------- retrieval ----------

def build_memory_block(agent, market_prices):
    m = agent["memory"]

    # recent non-failure activity
    acts = [e for e in m["episodic"] if e.get("kind") != "fail"]
    recent = "; ".join(f"c{e['cycle']} {e['text']}" for e in acts[-4:]) or "none yet"

    # v3: your OWN recent failed deals (private) — so you can price better next time
    fails = [e for e in m["episodic"] if e.get("kind") == "fail"][-3:]
    fails_str = "; ".join(e["text"] for e in fails) or "none"

    mkt = " ".join(f"{g}~{round(p, 1)}" for g, p in market_prices.items())
    own = []
    for g, prices in m["trade_prices"].items():
        if prices:
            own.append(f"{g} avg {round(sum(prices) / len(prices), 1)}")
    own_str = ("; ".join(own)) or "no trades yet"

    allies, rivals, neutral = [], [], []
    for oid in m["relationships"]:
        tag = classify(agent, oid)
        r = round(m["relationships"][oid]["R"], 2)
        entry = f"{oid}({r:+})"
        (allies if tag == "ally" else rivals if tag == "rival" else neutral).append(entry)

    return (
        f"Your recent activity: {recent}\n"
        f"Your recent FAILED deals (adjust your price next time): {fails_str}\n"
        f"Market prices: {mkt}\n"
        f"Your own recent trade prices: {own_str}\n"
        f"Allies: {', '.join(allies) or 'none'} | "
        f"Rivals: {', '.join(rivals) or 'none'} | "
        f"Neutral: {', '.join(neutral) or 'none'}"
    )
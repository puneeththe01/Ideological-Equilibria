"""
negotiation.py — real capped LLM haggle between a matched buyer and seller.

Drops into market.match_and_settle as negotiate_fn (same signature as the stub):
    llm_negotiate(buyer, seller, good, bid_price, ask_price, market_price, qty) -> float | None

Protocol (capped at 3 messages):
  1. buyer opens with a price offer
  2. seller accepts, or counters with a higher price
  3. buyer accepts the counter, or walks (-> None, orders roll over)

Each side reasons PRIVATELY with its own ideology, its relationship (R) toward
the other, and its own food/gold situation. Only PRICES cross between them —
neither sees the other's pantry — preserving the signalling/privacy design.
"""

import json, re, time
from config import client, MODEL, FOOD_PER_CYCLE, NEGOTIATION_CAP
from production import total_food
from memory import ensure_relationship, classify


def _safe_chat(system, user, max_tokens=120, max_retries=5):
    """Throttled LLM call with rate-limit (429) backoff, matching agent.py."""
    for attempt in range(max_retries):
        try:
            resp = client.chat.completions.create(
                model=MODEL,
                messages=[{"role": "system", "content": system},
                          {"role": "user", "content": user}],
                temperature=0.5, max_tokens=max_tokens,
            )
            time.sleep(1.6)
            return resp.choices[0].message.content.strip()
        except Exception as e:
            if "429" in str(e) or "RateLimit" in type(e).__name__:
                wait = 5 * (attempt + 1)
                print(f"    (negotiation rate limited, waiting {wait}s...)")
                time.sleep(wait)
            else:
                raise
    return ""


def _parse(raw):
    cleaned = re.sub(r"```(?:json)?", "", raw).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", cleaned, re.DOTALL)
        try:
            return json.loads(m.group(0)) if m else None
        except Exception:
            return None


def _runway(agent):
    return total_food(agent) // FOOD_PER_CYCLE


def _buyer_open(buyer, seller, good, market_price, qty):
    rel = ensure_relationship(buyer, seller["id"], seller["ideology"])
    tag = classify(buyer, seller["id"])
    i = buyer["ideology"]
    system = ('You are bargaining to BUY. Reply with ONLY JSON: '
              '{"offer": <number per unit>, "reason": "<few words>"}')
    user = f"""You are {buyer['id']} buying {qty} {good}.
Market price is about {round(market_price, 2)} per unit.
Your ideology: capitalism {i['capitalism']}, survivalism {i['survivalism']}, sustainability {i['sustainability']}.
Your relationship with seller {seller['id']}: {tag} (R={round(rel['R'], 2)}).
Your situation (private): {total_food(buyer)} food (~{_runway(buyer)} cycles left), {buyer['gold']} gold.
Make an opening price offer per unit. Bargain harder if you are capitalist; you may offer above market if you are desperate for food; offer an ally a fair price, a rival nothing generous."""
    d = _parse(_safe_chat(system, user, 100))
    if d and isinstance(d.get("offer"), (int, float)) and d["offer"] > 0:
        return float(d["offer"])
    return None


def _seller_respond(seller, buyer, good, market_price, qty, offer):
    rel = ensure_relationship(seller, buyer["id"], buyer["ideology"])
    tag = classify(seller, buyer["id"])
    i = seller["ideology"]
    system = ('You are bargaining to SELL. Reply with ONLY JSON: '
              '{"decision": "accept" | "counter", "price": <number or null>, "reason": "<few words>"}')
    user = f"""You are {seller['id']} selling {qty} {good}.
Market price is about {round(market_price, 2)} per unit.
Buyer {buyer['id']} offers {round(offer, 2)} per unit.
Your ideology: capitalism {i['capitalism']}, survivalism {i['survivalism']}, sustainability {i['sustainability']}.
Your relationship with buyer: {tag} (R={round(rel['R'], 2)}).
Your situation (private): {total_food(seller)} food, {seller['gold']} gold.
Accept if the offer is good enough, or counter with a higher price. Hold out for more if capitalist; sell fairly to an ally; you may gouge a rival."""
    d = _parse(_safe_chat(system, user, 100))
    if not d:
        return {"decision": "accept"}              # parse fail -> take the offer
    if d.get("decision") == "counter" and isinstance(d.get("price"), (int, float)) and d["price"] > 0:
        return {"decision": "counter", "price": float(d["price"])}
    return {"decision": "accept"}


def _buyer_final(buyer, seller, good, market_price, counter):
    i = buyer["ideology"]
    system = ('Reply with ONLY JSON: {"decision": "accept" | "reject", "reason": "<few words>"}')
    user = f"""You are {buyer['id']} buying {good}.
Market price is about {round(market_price, 2)} per unit. The seller counters at {round(counter, 2)} per unit.
Your ideology: capitalism {i['capitalism']}, survivalism {i['survivalism']}, sustainability {i['sustainability']}.
Your situation (private): {total_food(buyer)} food (~{_runway(buyer)} cycles left), {buyer['gold']} gold.
Accept if it is worth it (especially if you need the food), or reject to walk away."""
    d = _parse(_safe_chat(system, user, 80))
    if d and d.get("decision") == "reject":
        return False
    return True                                     # default: accept


def negotiate(buyer, seller, good, bid_price, ask_price, market_price, qty,
              buyer_open=_buyer_open, seller_respond=_seller_respond, buyer_final=_buyer_final):
    """Capped 3-message haggle. Returns agreed price per unit, or None (no deal)."""
    offer = buyer_open(buyer, seller, good, market_price, qty)
    if offer is None:
        offer = bid_price                           # fallback to the posted bid
    resp = seller_respond(seller, buyer, good, market_price, qty, offer)
    if resp["decision"] == "accept":
        return round(offer, 2)
    counter = resp.get("price", ask_price)
    if buyer_final(buyer, seller, good, market_price, counter):
        return round(counter, 2)
    return None


# real entry point used by the simulation
llm_negotiate = negotiate
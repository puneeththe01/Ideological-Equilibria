import json, re, time
from config import client, MODEL, FOOD_PER_CYCLE, NEGOTIATION_CAP
from production import total_food
from memory import ensure_relationship, classify


def _safe_chat(system, user, max_tokens=120, max_retries=5):
    for attempt in range(max_retries):
        try:
            resp = client.chat.completions.create(
                model=MODEL,
                messages=[{"role": "system", "content": system},
                          {"role": "user", "content": user}],
                temperature=0.5, max_tokens=max_tokens,
            )
            time.sleep(0.1)
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


def negotiate(buyer, seller, good, bid_price, ask_price, market_price, qty):
    if bid_price >= ask_price:
        return round((bid_price + ask_price) / 2, 2)
    rel = ensure_relationship(seller, buyer["id"], buyer["ideology"])
    tag = classify(seller, buyer["id"])
    i = seller["ideology"]
    system = ('You are bargaining to SELL. Reply with ONLY JSON: '
              '{"decision": "accept" | "counter" | "reject", "price": <number or null>}')
    user = f"""You are {seller['id']} selling {qty} {good}.
Market price is about {round(market_price, 2)} per unit.
Buyer {buyer['id']} offers {round(bid_price, 2)} per unit; your ask is {round(ask_price, 2)}.
Your ideology: capitalism {i['capitalism']}, survivalism {i['survivalism']}, sustainability {i['sustainability']}.
Your relationship with buyer: {tag} (R={round(rel['R'], 2)}).
Your situation (private): {total_food(seller)} food, {seller['gold']} gold.
Accept the buyer's offer, counter with one final price between {round(bid_price, 2)} and {round(ask_price, 2)}, or reject. Hold out for more if capitalist; sell fairly to an ally; you may gouge a rival."""
    d = _parse(_safe_chat(system, user, 60))
    if not d:
        return round((bid_price + ask_price) / 2, 2)
    decision = d.get("decision")
    if decision == "reject":
        return None
    if decision == "accept":
        return round(bid_price, 2)
    price = d.get("price")
    if isinstance(price, (int, float)) and price > 0:
        lo, hi = min(bid_price, ask_price), max(bid_price, ask_price)
        return round(max(lo, min(hi, float(price))), 2)
    return round((bid_price + ask_price) / 2, 2)


llm_negotiate = negotiate
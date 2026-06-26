import json
from agent import decide

agent = {
    "id": "AGT_007",
    "ideology": {
        "capitalism":      0.8,   # +1 = profit-maximising, -1 = anti-market
        "survivalism":     0.3,   # +1 = self-preservation at all costs
        "sustainability": -0.4,   # +1 = conserves shared resources, -1 = exploits them
    },
    "gold": 40,
    "food": 12,                   # below threshold -> creates pressure
}

if __name__ == "__main__":
    decision = decide(agent)
    print("PARSED DECISION:")
    print(json.dumps(decision, indent=2))
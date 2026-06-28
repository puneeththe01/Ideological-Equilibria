import json
from agent import decide

agent = {
    "id": "AGT_007",
    "ideology": {
        "capitalism":      0.8,   
        "survivalism":     0.3,   
        "sustainability": -0.4,   
    },
    "gold": 40,
    "food": 12,                   
}

if __name__ == "__main__":
    decision = decide(agent)
    print("PARSED DECISION:")
    print(json.dumps(decision, indent=2))
"""
config.py — single source of truth for the whole simulation.

v2 CHANGES vs previous:
  - LABOR is now a STORABLE bank: LABOR_RANGE -> LABOR_REFRESH_RANGE + new LABOR_CAP (80).
  - CROPS gained per-crop `spoil` and `harvest_risk` rates.
  - New scarcity blocks: inventory upkeep, plot upkeep + health, spoilage ramp.
  - Everything else (market, memory, negotiation constants) unchanged.
"""

import os
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

API_KEY = os.getenv("NVIDIA_API_KEY")
if not API_KEY:
    raise RuntimeError("NVIDIA_API_KEY not found. Create a .env file with your key.")
if not API_KEY.startswith("nvapi-"):
    print("Warning: key does not start with 'nvapi-' — double-check it.")

client = OpenAI(base_url="https://integrate.api.nvidia.com/v1", api_key=API_KEY)
MODEL = "meta/llama-3.1-8b-instruct"

# ---------- Survival ----------
FOOD_PER_CYCLE = 5
DEATH_STARVATION = 20

# ---------- Starting endowment ----------
STARTING_GOLD = 50
STARTING_WATER = 12
STARTING_FOOD = {"wheat": 20, "rice": 16, "corn": 30}

# ---------- Labor: STORABLE bank (v2) ----------
LABOR_REFRESH_RANGE = (8, 12)   # added to the bank each cycle (was use-it-or-lose-it)
LABOR_CAP = 80                  # bank cannot exceed this

# ---------- Water ----------
WATER_REGEN_RANGE = (3, 7)
WATER_CAP_INITIAL = 20
WATER_CAP_EXPANSION = 10
WATER_CAP_EXPANSION_COST = 15

# ---------- Crops (v2: + spoil, + harvest_risk) ----------
# req_water/req_labor = TOTAL inputs to mature one plot.
# spoil = fraction of stored stock lost per cycle.
# harvest_risk = chance of an underyield event (fast crop = riskiest).
CROPS = {
    "wheat": {"req_water": 4,  "req_labor": 8,  "yield_range": (5, 9),   "spoil": 0.01,  "harvest_risk": 0.20},
    "corn":  {"req_water": 8,  "req_labor": 18, "yield_range": (9, 15),  "spoil": 0.05,  "harvest_risk": 0.10},
    "rice":  {"req_water": 18, "req_labor": 12, "yield_range": (14, 22), "spoil": 0.005, "harvest_risk": 0.05},
}

# ---------- Inventory upkeep (v2): 1 labor per (threshold) units held, summed, at cycle start ----------
INV_UPKEEP_THRESHOLD = {"wheat": 50, "corn": 200, "rice": 400}
SPOIL_RAMP_PER_CYCLE = 0.02     # unpaid inventory upkeep adds +2% spoilage per crop per cycle, stacking

# ---------- Plot upkeep + health (v2) ----------
PLOT_UPKEEP_LABOR = 1           # labor per growing plot per cycle
PLOT_UPKEEP_GOLD = 1            # gold per growing plot per cycle
PLOT_HEALTH_START = 100
PLOT_HEALTH_DECAY = 25          # health lost per unpaid cycle (4 cycles of neglect -> death)
PLOT_SCAR_THRESHOLD = 70        # if health ever dips below this, the harvest is scarred
PLOT_SCAR_PENALTY = 0.30        # 30% yield cut if scarred
DEAD_PLOT_CLEAR_GOLD = 2        # gold to clear a dead plot

# ---------- Market ----------
TRADABLE_GOODS = ["wheat", "rice", "corn", "water", "labor", "kernels"]
SEED_PRICES = {"rice": 8, "wheat": 4, "corn": 6, "water": 2, "labor": 3, "kernels": 8.4}
ORDER_EXPIRY = 3
MATCH_TOLERANCE = 0.30
NEGOTIATION_CAP = 3
DEFAULT_ALLOW_PARTIAL = True

# ---------- Relationships / memory ----------
EPISODIC_WINDOW = 10
R_DECAY = 0.98
AFFINITY_WEIGHT = 0.30
ALLY_THRESHOLD = 0.35
RIVAL_THRESHOLD = -0.35
DEFAULT_PERSONALITY = {
    "trust_gain": 1.0,
    "wariness": 1.0,
    "gossip_susceptibility": 1.0,
    "ally_threshold": ALLY_THRESHOLD,
    "rival_threshold": RIVAL_THRESHOLD,
}

# ---------- Cognitive dissonance (v4) ----------
DISSONANCE_DECAY = 0.85        # gamma: exponential decay on accumulated dissonance
DISSONANCE_THRESHOLD = 0.6     # theta: ΔD level that triggers rationalisation
MUTATION_STEP = 0.18           # how far ideology nudges toward behaviour when it fires (gentle)

# ---------- Food Processing Unit + kernels (v5) ----------
KERNEL_SPOIL = 0.005          # kernels spoil slowly (0.5%/cycle)
KERNEL_FOOD_VALUE = 1.5       # each kernel = 1.5 food when eaten
KERNEL_SEED_STOCK = 40        # unit starts with this many kernels
UNIT_BUY_RATE = 0.70          # unit pays 70% of corn market price for raw corn (reduced faucet)
KERNEL_SELL_MARKUP = 1.10     # unit sells kernels at 1.1x the KERNEL market price
PROCESS_GOLD_PER_10 = 1.0     # processing fee: gold per 10 corn
PROCESS_LABOR_PER_10 = 1.0    # processing fee: labor per 10 corn

# ---------- Price-from-pressure mechanism (v6) ----------
TRADE_PULL = 0.5         # how far price moves toward this cycle's executed VWAP (trades weighted more)
PRICE_PRESSURE_K = 0.1   # sensitivity to (bid-ask)/(bid+ask) demand pressure
PRICE_MAX_MOVE = 0.15    # max +/- price move per cycle (15%)
PRICE_FLOOR = 0.5        # absolute price floor so nothing collapses to zero

# ---------- Land market + Bank (v7) ----------
TOTAL_PLOTS = 30            # total ownable land parcels in the world (for 20 agents)
PLOT_BASE_PRICE = 30.0      # base/"original" land value (also the bank resale price)
PLOT_PRICE_K = 1.0         # price climbs with scarcity: price = base*(1 + k*fraction_taken)
PLOT_COLLATERAL_FRAC = 0.70  # a plot is worth 70% of its purchase price as collateral

DEPOSIT_RATE = 0.01        # deposit interest per cycle (lowered to curb inflation)
LOAN_BASE_RATE = 0.02      # safe loan interest per cycle
LOAN_MAX_RATE = 0.10       # riskiest loan interest per cycle
FREE_LOAN_LIMIT = 50.0     # gold any agent may borrow with no collateral/asset check (still 2%)
ASSET_LOAN_MULTIPLE = 5    # uncollateralised borrow ceiling = 5x (gold+food value)
MISSED_PAYMENTS_TO_SEIZE = 5   # consecutive no-payment cycles before the bank seizes
FORECLOSURE_CYCLES = 10        # cycles after seizure before the plot is permanently the bank's
FOOD_SEIZE_FRAC = 0.25         # food seizure cap = 25% of the loan (for plot-less defaulters)
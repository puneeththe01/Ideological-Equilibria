"""
respawn.py — evolutionary death-birth (Moran-style) replacement.

When an agent dies, a successor is born with a fresh sequential ID starting at 101.
Following the standard death-birth process used in evolutionary agent-based models,
the successor INHERITS the ideology of a successful LIVING agent (chosen with
probability proportional to gold = fitness), with a small random MUTATION on each
axis. This turns death into selection pressure: ideologies that prosper get copied,
ideologies that fail die out, so the population evolves over a long run.

The newborn's starting endowment is NEW MONEY entering the economy, so it is kept
modest and TRACKED (see RespawnManager totals) to preserve the money-supply work.
"""

import random
from production import new_agent
from memory import new_memory
from config import (
    STARTING_FOOD, STARTING_GOLD, RESPAWN_GOLD, RESPAWN_FOOD_FRAC,
    RESPAWN_MUTATION, RESPAWN_RANDOM_CHANCE,
)

AXES = ("capitalism", "survivalism", "sustainability")


class RespawnManager:
    def __init__(self, rng=None, next_id=101):
        self.rng = rng or random.Random()
        self.next_id = next_id
        self.births = 0
        self.gold_injected = 0.0      # money created by newborn endowments (a tracked faucet)
        self.lineage = []             # (new_id, parent_id_or_None, dead_id)

    def _pick_parent(self, living):
        """Fitness-proportional choice: gold is fitness. Falls back to uniform."""
        weights = [max(0.0, a["gold"]) for a in living]
        total = sum(weights)
        if total <= 0:
            return self.rng.choice(living)
        r = self.rng.uniform(0, total)
        upto = 0.0
        for a, w in zip(living, weights):
            upto += w
            if upto >= r:
                return a
        return living[-1]

    def _inherit_ideology(self, parent):
        ideo = {}
        for ax in AXES:
            base = parent["ideology"][ax]
            mutated = base + self.rng.uniform(-RESPAWN_MUTATION, RESPAWN_MUTATION)
            ideo[ax] = round(max(-1.0, min(1.0, mutated)), 3)
        return ideo

    def _random_ideology(self):
        return {ax: round(self.rng.uniform(-1, 1), 3) for ax in AXES}

    def spawn(self, dead_agent, living, cycle):
        """Create and return one successor agent for a dead agent."""
        new_id = f"AGT_{self.next_id}"
        self.next_id += 1

        # mostly inherit from a successful living agent; occasionally a fresh random newcomer
        if living and self.rng.random() > RESPAWN_RANDOM_CHANCE:
            parent = self._pick_parent(living)
            ideo = self._inherit_ideology(parent)
            parent_id = parent["id"]
            desc = (f"{new_id}, a newcomer who took up the trade of {parent_id} "
                    f"after {dead_agent['id']} starved.")
        else:
            ideo = self._random_ideology()
            parent_id = None
            desc = f"{new_id}, a drifter who arrived after {dead_agent['id']} starved."

        a = new_agent(new_id, ideo, gold=RESPAWN_GOLD)
        # modest food endowment (a fraction of the normal start) so a newborn isn't instantly dying
        a["inventory"] = {k: int(v * RESPAWN_FOOD_FRAC) for k, v in STARTING_FOOD.items()}
        a["inventory"]["kernels"] = 0
        a["memory"] = new_memory()
        a["description"] = desc
        a["dissonance"] = 0.0

        # track the new money this endowment injects (gold only; food isn't money)
        self.gold_injected += RESPAWN_GOLD
        self.births += 1
        self.lineage.append((new_id, parent_id, dead_agent["id"]))
        return a
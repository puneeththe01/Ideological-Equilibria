import os
import pickle

CHECKPOINT_PATH = "sim_checkpoint.pkl"


def save_checkpoint(cycle, rng, agents, book, unit, land, bank, respawner,
                    path=CHECKPOINT_PATH):
    state = {
        "cycle": cycle,
        "rng": rng.getstate(),
        "agents": agents,
        "book": book,
        "unit": unit,
        "land": land,
        "bank": bank,
        "respawner": respawner,
    }
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        pickle.dump(state, f, protocol=pickle.HIGHEST_PROTOCOL)
    os.replace(tmp, path)   # atomic: a crash mid-write never corrupts the good checkpoint


def load_checkpoint(path=CHECKPOINT_PATH):
    if not os.path.exists(path):
        return None
    with open(path, "rb") as f:
        return pickle.load(f)


def checkpoint_exists(path=CHECKPOINT_PATH):
    return os.path.exists(path)
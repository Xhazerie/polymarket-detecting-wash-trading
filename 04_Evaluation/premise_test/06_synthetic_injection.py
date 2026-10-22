"""Step 6 (evaluation; role B): synthetic wash-trader injection + precision@k.

The premise test shows Algorithm 1 flags far more volume in a known-dirty week
(Dec 2024) than a known-quiet week (Jun 2025). That is strong but *indirect*
evidence: the two weeks differ in many ways besides wash trading, and we never
see the detector's output against a known answer.

This step supplies that answer. We plant K wash rings with known membership into
the quiet Jun-2025 window and ask how well the score recovers exactly those
wallets. Because real wash in that window is low (~0.35% of volume at theta=0.9),
the injected rings should dominate the top of the ranking if the detector works.

Ground truth
------------
A wash ring is a small cycle of wallets that trade a position back and forth:
each wallet opens a position against one ring neighbour and closes it against the
same neighbour, over and over, so (a) every ring wallet "closes" in every market
it touches (high x0) and (b) its counterparty volume is concentrated on its one
or two ring neighbours (high B weight). That is exactly the pattern Algorithm 1
scores, and it matches the EDA finding that Dec wash wallets split ~50/50 between
two partners.

To make recall@theta informative rather than a foregone conclusion, rings are
injected at a range of *wash intensities*. A ring at intensity w also does some
legitimate volume (open-and-hold trades against fresh outsiders, which never
close), so each ring wallet's wash fraction x0 is about w. A perfect detector
flags high-intensity rings and lets low-intensity ones slip below theta, tracing
out a precision/recall trade-off.

The injected rings are a disconnected component of the trade graph, so they do
not change any real wallet's score: the combined run's real-wallet scores are
identical to the base window's. Real wallets that still rank above an injected
wallet are either genuine (unlabelled) wash or false positives; we report that
count as a *conservative* precision, since some of those are real wash we cannot
credit.

Run:  uv run python 04_Evaluation/premise_test/06_synthetic_injection.py
"""

import importlib.util
import json
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from config import INTERIM, RESULTS, THETA

# --- Load the shared scoring logic from 02_alg1.py (not an importable name). ---
_ALG1 = Path(__file__).resolve().parent / "02_alg1.py"
_spec = importlib.util.spec_from_file_location("alg1", _ALG1)
alg1 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(alg1)

# --- Injection design (reproducible; tune here) ---------------------------------
BASE_WINDOW = "jun2025"   # inject into the quiet window so ground truth is clean
SEED = 20251022
RINGS_PER_LEVEL = 8       # wash rings planted at each intensity level
RING_SIZE = 3             # wallets per ring (cycle length; 2 = a simple pair)
ROUND_TRIPS = 3           # open+close cycles per ring edge
WASH_SHARES = 1000.0      # shares per leg of a wash round trip
# Each wallet's wash fraction x0 ~ intensity; theta sits inside this range so the
# evaluation measures a real precision/recall trade-off, not a sure thing.
INTENSITY_LEVELS = (1.0, 0.95, 0.90, 0.85, 0.80, 0.70)

# Synthetic ids use non-hex characters so they can never collide with a real
# 0x+40-hex address or a real condition id, and are easy to identify.
WASH_WALLET = "0xwash_{lvl}_{ring}_{node}"
OUTSIDER_WALLET = "0xoutsider_{lvl}_{ring}_{node}_{k}"
WASH_MARKET = "0xmkt_wash_{lvl}_{ring}_{edge}"
HOLD_MARKET = "0xmkt_hold_{lvl}_{ring}_{node}"


def build_injection() -> tuple[pd.DataFrame, set[str]]:
    """Return (synthetic trade rows matching the trades schema, set of wash wallets).

    Only the columns Algorithm 1 reads are produced:
    block, log_index, market, maker, taker, shares, dp_maker, in_target.
    """
    rows = []
    wash_wallets: set[str] = set()
    block = 900_000_000  # far above any real block, and strictly increasing per row

    for lvl_i, intensity in enumerate(INTENSITY_LEVELS):
        for ring in range(RINGS_PER_LEVEL):
            nodes = [WASH_WALLET.format(lvl=lvl_i, ring=ring, node=j) for j in range(RING_SIZE)]
            wash_wallets.update(nodes)
            # Track each wallet's wash volume so we can size its legit dilution.
            wash_vol = {w: 0.0 for w in nodes}

            # Wash edges: a cycle a->b->c->a. For RING_SIZE==2 this is two edges
            # between the same pair, placed in two separate markets.
            for edge in range(RING_SIZE):
                a, b = nodes[edge], nodes[(edge + 1) % RING_SIZE]
                market = WASH_MARKET.format(lvl=lvl_i, ring=ring, edge=edge)
                for _ in range(ROUND_TRIPS):
                    # open: a goes long WASH_SHARES, b goes short (dp is the maker's)
                    rows.append((block, market, a, b, WASH_SHARES, +WASH_SHARES, True))
                    block += 1
                    # close: a returns to flat (terminal contraction to 0 => closure)
                    rows.append((block, market, a, b, WASH_SHARES, -WASH_SHARES, True))
                    block += 1
                    wash_vol[a] += 2 * WASH_SHARES
                    wash_vol[b] += 2 * WASH_SHARES

            # Legit dilution: give each ring wallet open-and-hold volume so its wash
            # fraction is ~intensity. The hold never closes (single open, m_before=0),
            # so it adds to the denominator of x0 but not the numerator.
            if intensity < 1.0:
                for j, w in enumerate(nodes):
                    legit = wash_vol[w] * (1.0 - intensity) / intensity
                    if legit <= 0:
                        continue
                    outsider = OUTSIDER_WALLET.format(lvl=lvl_i, ring=ring, node=j, k=0)
                    market = HOLD_MARKET.format(lvl=lvl_i, ring=ring, node=j)
                    # w buys `legit` shares and holds; outsider takes the other side.
                    rows.append((block, market, w, outsider, legit, +legit, True))
                    block += 1

    synth = pd.DataFrame(
        rows, columns=["block", "market", "maker", "taker", "shares", "dp_maker", "in_target"]
    )
    synth.insert(1, "log_index", 0)  # keep (block, log_index) ordering identical to real rows
    return synth, wash_wallets


def average_precision(score: np.ndarray, is_pos: np.ndarray) -> float:
    """Average precision treating is_pos as the only positives.

    Ties in score are broken conservatively: a real wallet at the same score as an
    injected one is ranked ahead of it, so it counts against precision.
    """
    order = np.lexsort((is_pos.astype(int), -score))  # primary -score, then real-first
    hits = is_pos[order]
    n_pos = int(hits.sum())
    if n_pos == 0:
        return 0.0
    cum_tp = np.cumsum(hits)
    precision_at = cum_tp / (np.arange(len(hits)) + 1)
    return float(precision_at[hits].sum() / n_pos)


def precision_at_k(score: np.ndarray, is_pos: np.ndarray, ks: list[int]) -> dict:
    order = np.lexsort((is_pos.astype(int), -score))
    hits = is_pos[order]
    cum_tp = np.cumsum(hits)
    return {str(k): round(float(cum_tp[k - 1] / k), 4) for k in ks if k <= len(hits)}


def evaluate() -> dict:
    base = INTERIM / f"{BASE_WINDOW}_trades.parquet"
    if not base.exists():
        raise FileNotFoundError(
            f"{base} not found. Run 01_extract.py first to build the base window."
        )

    np.random.seed(SEED)  # reserved for future randomised variants; current build is deterministic
    synth, wash_wallets = build_injection()

    INTERIM.mkdir(parents=True, exist_ok=True)
    injected_path = INTERIM / f"{BASE_WINDOW}_injected_trades.parquet"

    cols = "block, log_index, market, maker, taker, shares, dp_maker, in_target"
    with duckdb.connect() as con:
        con.register("synth", synth)
        con.execute(f"""
            COPY (
                SELECT {cols} FROM '{base}'
                UNION ALL
                SELECT {cols} FROM synth
            ) TO '{injected_path}' (FORMAT parquet)
        """)

        s = alg1.score_wallets(con, str(injected_path))

    wallets, x = s["wallets"], s["x"]
    is_pos = np.array([w in wash_wallets for w in wallets])
    n_pos = int(is_pos.sum())
    assert n_pos == len(wash_wallets), "some injected wallets vanished from the scored set"

    # Per-intensity recall at the fixed threshold: the share of each level's wallets
    # the theta rule flags. Intensity is encoded in the wallet id ("0xwash_<lvl>_...").
    by_level = {}
    for lvl_i, intensity in enumerate(INTENSITY_LEVELS):
        prefix = f"0xwash_{lvl_i}_"
        mask = np.array([w.startswith(prefix) for w in wallets])
        scores = x[mask]
        by_level[f"{intensity:.2f}"] = {
            "wallets": int(mask.sum()),
            "recall_at_theta": round(float((scores >= THETA).mean()), 4),
            "median_score": round(float(np.median(scores)), 4),
            "min_score": round(float(scores.min()), 4),
        }

    injected_scores = x[is_pos]
    real_above_min = int(((~is_pos) & (x >= injected_scores.min())).sum())

    ks = [n_pos, 2 * n_pos, 5 * n_pos]
    return {
        "base_window": BASE_WINDOW,
        "theta": THETA,
        "design": {
            "rings_per_level": RINGS_PER_LEVEL,
            "ring_size": RING_SIZE,
            "round_trips": ROUND_TRIPS,
            "intensity_levels": list(INTENSITY_LEVELS),
            "wash_shares_per_leg": WASH_SHARES,
        },
        "wallets_total": int(len(wallets)),
        "wash_wallets_injected": n_pos,
        "recall_at_theta_overall": round(float((injected_scores >= THETA).mean()), 4),
        "average_precision": round(average_precision(x, is_pos), 4),
        "precision_at_k": precision_at_k(x, is_pos, ks),
        "real_wallets_scoring_above_lowest_injected": real_above_min,
        "recall_at_theta_by_intensity": by_level,
        "note": (
            "recall_at_theta_by_intensity should fall as intensity drops past theta; "
            "precision is conservative because unlabelled real wash in the base window "
            "counts as a false positive."
        ),
    }


def main() -> None:
    RESULTS.mkdir(parents=True, exist_ok=True)
    out = evaluate()
    print(json.dumps(out, indent=2, default=float))
    (RESULTS / "synthetic_injection.json").write_text(json.dumps(out, indent=2, default=float))


if __name__ == "__main__":
    main()

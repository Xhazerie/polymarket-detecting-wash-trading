"""Step 7 (algorithm output; role B): per-wallet scores and flags for EDA round 2.

The premise test (02_alg1.py) reports window-level numbers only. EDA round 2 needs
to compare *flagged vs unflagged wallets*, and the per-market theta-sensitivity needs
a wallet's score to hand. Both want the same artifact: one row per wallet, with its
Algorithm 1 score and the features EDA already builds from the trades.

For each window this writes results/wallet_flags/<window>.parquet with:
  wallet            address
  x                 final Algorithm 1 score in [0, 1]
  x0                initial score (wash share of the wallet's volume)
  flagged           x >= THETA (the wallet-level flag)
  target_vol        target-week share volume the wallet took part in (either side)
  target_wash_vol   of that, volume in trades where BOTH ends score >= THETA
  in_wash_trade     target_wash_vol > 0 (the wallet actually produced wash volume)
  n_markets         distinct target-week markets the wallet traded
  n_counterparties  distinct target-week counterparties

Lead-in-only wallets (no target-week trade) keep their score but get zero target
features. Per-wallet target_vol counts a trade once for each of its two wallets, so
it is "volume the wallet participated in", not a partition of system volume; the
summary's volume figures use the once-per-trade convention to match alg1_results.

Run:  uv run python 04_Evaluation/premise_test/07_wallet_flags.py
"""

import importlib.util
import json
from pathlib import Path

import duckdb
import pandas as pd

from config import INTERIM, RESULTS, THETA, WINDOWS

_ALG1 = Path(__file__).resolve().parent / "02_alg1.py"
_spec = importlib.util.spec_from_file_location("alg1", _ALG1)
alg1 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(alg1)


def wallet_flags(con: duckdb.DuckDBPyConnection, name: str, out_dir: Path) -> dict:
    trades = str(INTERIM / f"{name}_trades.parquet")
    s = alg1.score_wallets(con, trades)
    con.register("score", pd.DataFrame({"wallet": s["wallets"], "x": s["x"], "x0": s["x0"]}))

    # Per-wallet target-week features. Each target trade contributes to both its
    # maker and its taker (UNION ALL), so a wallet's volume counts every trade it is in.
    con.execute(f"""
        CREATE OR REPLACE TEMP TABLE wallet_target AS
        WITH flagged_trades AS (
            SELECT t.maker, t.taker, t.market, t.shares,
                   least(a.x, b.x) >= {THETA} AS wash
            FROM '{trades}' t
            JOIN score a ON a.wallet = t.maker
            JOIN score b ON b.wallet = t.taker
            WHERE t.in_target
        ),
        sides AS (
            SELECT maker AS wallet, taker AS cp, market, shares, wash FROM flagged_trades
            UNION ALL
            SELECT taker AS wallet, maker AS cp, market, shares, wash FROM flagged_trades
        )
        SELECT wallet,
               sum(shares)             AS target_vol,
               sum(shares) FILTER (wash) AS target_wash_vol,
               count(DISTINCT market)  AS n_markets,
               count(DISTINCT cp)      AS n_counterparties
        FROM sides GROUP BY wallet
    """)

    out = out_dir / f"{name}.parquet"
    con.execute(f"""
        COPY (
            SELECT s.wallet, s.x, s.x0,
                   s.x >= {THETA}                      AS flagged,
                   coalesce(w.target_vol, 0)           AS target_vol,
                   coalesce(w.target_wash_vol, 0)      AS target_wash_vol,
                   coalesce(w.target_wash_vol, 0) > 0  AS in_wash_trade,
                   coalesce(w.n_markets, 0)            AS n_markets,
                   coalesce(w.n_counterparties, 0)     AS n_counterparties
            FROM score s LEFT JOIN wallet_target w USING (wallet)
        ) TO '{out}' (FORMAT parquet)
    """)

    # Window summary. Volume figures use the once-per-trade convention so they match
    # 02_alg1.py's target_share_volume / target_wash_share_volume exactly.
    vol = con.sql(f"""
        SELECT sum(t.shares)                                   AS target_vol,
               sum(t.shares) FILTER (least(a.x, b.x) >= {THETA}) AS target_wash_vol
        FROM '{trades}' t
        JOIN score a ON a.wallet = t.maker
        JOIN score b ON b.wallet = t.taker
        WHERE t.in_target
    """).fetchone()
    wc = con.sql(f"""
        SELECT count(*) AS wallets,
               count(*) FILTER (x >= {THETA}) AS flagged_wallets
        FROM score
    """).fetchone()
    target_vol = vol[0] or 0.0
    return {
        "window": name,
        "wallets": wc[0],
        "flagged_wallets": wc[1],
        "flagged_wallet_share": round(wc[1] / wc[0], 4) if wc[0] else 0.0,
        "target_share_volume": target_vol,
        "target_wash_share_volume": vol[1] or 0.0,
        "wash_volume_share": round((vol[1] or 0.0) / target_vol, 4) if target_vol else 0.0,
        "output": str(out.relative_to(RESULTS.parent)),
    }


def main() -> None:
    out_dir = RESULTS / "wallet_flags"
    out_dir.mkdir(parents=True, exist_ok=True)
    with duckdb.connect() as con:
        summary = [wallet_flags(con, name, out_dir) for name in WINDOWS]
    print(json.dumps(summary, indent=2, default=float))
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2, default=float))


if __name__ == "__main__":
    main()

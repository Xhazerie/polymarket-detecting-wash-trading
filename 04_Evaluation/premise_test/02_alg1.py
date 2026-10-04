"""Step 2 (algorithm; role B takes over in phase 2): Algorithm 1 of Sirolly et al. (2025) at a fixed threshold.

Part I  — initial score x0_i = sum over markets m of s_im * 1{Q_im > 0}
          s_im = share of wallet i's volume traded in market m
          Q_im > 0 = wallet i "closed" a position at least once in market m
Part II — iterate x <- (x0 + B x) / 2 until the relative L2 change < tol
          B[i, j] = fraction of i's share volume traded against j (row-stochastic)
Flag    — a trade is wash if both wallets end with score >= theta

Closure test, done in SQL for speed (tens of millions of ledger rows):
we only need to know *whether* a closure exists, not how many. The first
closure is measured against the running max since the start, so
  Q_im > 0  <=>  some trade reverses the position (long->short or back; the paper
                 splits it into "down to 0" + "reopen", and 0 <= c*M always), OR
                 some terminal contraction t has |P_t| <= c * max(|P_s|, s < t).
A terminal contraction shrinks |P| and is either the wallet's last trade in the
market or is followed by a trade that grows |P| again.

Run:  uv run python 04_Evaluation/premise_test/02_alg1.py
"""

import json

import duckdb
import numpy as np
import pandas as pd
import scipy.sparse as sp

from config import C_CLOSURE, GO_PEAK_MIN, GO_QUIET_MAX, INTERIM, RESULTS, THETA, TOL, WINDOWS


def closure_flags(con: duckdb.DuckDBPyConnection, trades: str) -> None:
    """Build wm(wallet, market, vol, q): one row per wallet x market."""
    # Ledger: every trade appears twice, once per side, with that side's position change.
    con.execute(f"""
        CREATE OR REPLACE TEMP TABLE ledger AS
        SELECT maker AS wallet, market, block, log_index, dp_maker AS dp, shares FROM '{trades}'
        UNION ALL
        SELECT taker AS wallet, market, block, log_index, -dp_maker AS dp, shares FROM '{trades}'
    """)
    con.execute(f"""
        CREATE OR REPLACE TEMP TABLE wm AS
        WITH pos AS (
            SELECT wallet, market, shares, dp,
                   row_number() OVER w AS rn,
                   sum(dp) OVER w AS p            -- net long position after this trade
            FROM ledger
            WINDOW w AS (PARTITION BY wallet, market ORDER BY block, log_index
                         ROWS UNBOUNDED PRECEDING)
        ),
        steps AS (
            SELECT *,
                   abs(p) AS x,
                   abs(p - dp) AS x_prev,
                   sign(p) * sign(p - dp) < 0 AS reversal,
                   -- M: largest |position| before this trade
                   coalesce(max(abs(p)) OVER (PARTITION BY wallet, market ORDER BY rn
                            ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING), 0) AS m_before
            FROM pos
        ),
        nxt AS (
            SELECT *,
                   lead(x) OVER (PARTITION BY wallet, market ORDER BY rn) AS x_next,
                   lead(reversal) OVER (PARTITION BY wallet, market ORDER BY rn) AS rev_next
            FROM steps
        )
        SELECT wallet, market, sum(shares) AS vol,
               bool_or(
                   reversal
                   OR (x < x_prev AND NOT reversal                       -- contraction
                       AND (x_next IS NULL OR (x_next > x AND NOT rev_next))  -- terminal
                       AND m_before > 0 AND x <= {C_CLOSURE} * m_before) -- deep enough drawdown
               ) AS q
        FROM nxt
        GROUP BY wallet, market
    """)


def run_window(con: duckdb.DuckDBPyConnection, name: str) -> dict:
    trades = str(INTERIM / f"{name}_trades.parquet")
    closure_flags(con, trades)

    # Wallet index
    wallets = con.sql("SELECT DISTINCT wallet FROM wm ORDER BY wallet").df()["wallet"].to_numpy()
    idx = {w: i for i, w in enumerate(wallets)}
    n = len(wallets)

    # Part I: x0_i = sum_m s_im * 1{Q_im > 0}
    x0_df = con.sql("""
        SELECT wallet, sum(vol) FILTER (q) / sum(vol) AS x0 FROM wm GROUP BY wallet
    """).df()
    x0 = np.zeros(n)
    x0[x0_df["wallet"].map(idx).to_numpy()] = x0_df["x0"].fillna(0).to_numpy()

    # Part II: B from pair volumes, summed over all markets, made symmetric
    pairs = con.sql(f"""
        SELECT maker, taker, sum(shares) AS v FROM '{trades}' GROUP BY 1, 2
    """).df()
    r = pairs["maker"].map(idx).to_numpy()
    c = pairs["taker"].map(idx).to_numpy()
    v = pairs["v"].to_numpy()
    W = sp.coo_matrix((np.r_[v, v], (np.r_[r, c], np.r_[c, r])), shape=(n, n)).tocsr()
    deg = np.asarray(W.sum(axis=1)).ravel()
    B = sp.diags(1.0 / np.where(deg > 0, deg, 1.0)) @ W

    x = x0.copy()
    for k in range(1, 1000):
        x_new = 0.5 * (x0 + B @ x)
        rel = np.linalg.norm(x_new - x) / max(np.linalg.norm(x), 1e-12)
        x = x_new
        if rel < TOL:
            break

    # Property from the paper (Prop. 2): the volume-weighted mean score is conserved.
    vw_x0, vw_x = float(deg @ x0 / deg.sum()), float(deg @ x / deg.sum())

    # Flag target-week trades where both wallets score >= theta
    con.register("score", pd.DataFrame({"wallet": wallets, "x": x}))
    res = con.sql(f"""
        SELECT sum(t.shares) AS vol,
               sum(t.shares) FILTER (least(a.x, b.x) >= {THETA}) AS wash_vol
        FROM '{trades}' t
        JOIN score a ON a.wallet = t.maker
        JOIN score b ON b.wallet = t.taker
        WHERE t.in_target
    """).fetchone()
    # Sensitivity: the same fraction at other fixed thresholds (paper Fig. 6/7 style)
    sens = con.sql(f"""
        SELECT th, sum(t.shares) FILTER (least(a.x, b.x) >= th) / sum(t.shares) AS frac
        FROM '{trades}' t
        JOIN score a ON a.wallet = t.maker
        JOIN score b ON b.wallet = t.taker
        CROSS JOIN (SELECT unnest([0.7, 0.8, 0.9, 0.95, 0.99]) AS th)
        WHERE t.in_target
        GROUP BY th ORDER BY th
    """).fetchall()
    closures = con.sql("SELECT avg(q::INT), count(*) FROM wm").fetchone()

    return {
        "window": name,
        "wallets": n,
        "wallet_market_pairs": closures[1],
        "share_of_wallet_markets_with_closure": round(closures[0], 4),
        "iterations": k,
        "vol_weighted_score_x0": round(vw_x0, 4),
        "vol_weighted_score_final": round(vw_x, 4),
        "target_share_volume": res[0],
        "target_wash_share_volume": res[1] or 0.0,
        "wash_fraction_theta_0.9": round((res[1] or 0.0) / res[0], 4),
        "wash_fraction_by_theta": {str(t): round(f or 0.0, 4) for t, f in sens},
    }


def main() -> None:
    con = duckdb.connect()
    out = {name: run_window(con, name) for name in WINDOWS}
    peak, quiet = out["dec2024"]["wash_fraction_theta_0.9"], out["jun2025"]["wash_fraction_theta_0.9"]
    out["verdict"] = {
        "peak_dec2024": peak,
        "quiet_jun2025": quiet,
        "rule": f"GO if peak >= {GO_PEAK_MIN} and quiet <= {GO_QUIET_MAX}",
        "go": bool(peak >= GO_PEAK_MIN and quiet <= GO_QUIET_MAX),
    }
    print(json.dumps(out, indent=2, default=float))
    (RESULTS / "alg1_results.json").write_text(json.dumps(out, indent=2, default=float))


if __name__ == "__main__":
    main()

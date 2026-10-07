"""Compare sampled trade-derived positions with an alternate raw-fill ledger.

Run: uv run python 04_Evaluation/premise_test/04_validate_positions.py

The cleaned ledger derives taker changes by negating maker changes. The reference
instead books each raw fill to its own maker, INCLUDING exchange-summary rows:
those rows describe the taker's actual order. Matching block-level changes checks
this reconstruction without assuming that every taker change is -dp_maker.

Both ledgers start at zero at the lead-in boundary and describe trading exposure,
not actual historical token balances. user_position is a later state snapshot and
cannot provide ground truth at our 2024/2025 window endpoints.
"""

import argparse
import json

import duckdb

from config import INTERIM, RAW, RESULTS, WEEKLY_WINDOWS


def check_window(con: duckdb.DuckDBPyConnection, name: str, window: dict, size: int) -> dict:
    con.read_parquet(str(INTERIM / f"{name}_trades.parquet")).create_view("trades", replace=True)
    # Deterministic sample across BOTH sides; ordering by a hash avoids selecting
    # just the first addresses. The same sample can be reproduced on another run.
    con.execute("""
        CREATE OR REPLACE TEMP TABLE sample AS
        SELECT wallet, market FROM (
            SELECT maker AS wallet, market FROM trades
            UNION
            SELECT taker AS wallet, market FROM trades
        ) ORDER BY md5(wallet || market) LIMIT ?
    """, [size])

    files = [str(RAW / "order_filled" / f"{month}.parquet") for month in window["months"]]
    con.read_parquet(files).create_view("raw_fills", replace=True)

    # An alternate ledger uses the actual token and direction in each wallet's
    # own order. Do not remove exchange-summary rows here: removing them would
    # remove the taker's own orders and invalidate this reference calculation.
    # Work in integer microshares to avoid floating-point accumulation errors.
    con.execute("""
        CREATE OR REPLACE TEMP TABLE raw_blocks AS
        SELECT s.wallet, s.market,
            CAST(split_part(r.id, '_', 2) AS BIGINT) AS block,
            sum((CASE WHEN r.makerAssetId = '0'
                THEN CAST(r.takerAmountFilled AS HUGEINT)
                ELSE -CAST(r.makerAmountFilled AS HUGEINT) END) * t.sign) AS units
        FROM raw_fills r
        JOIN reference_tokens t ON t.token = CASE
            WHEN r.makerAssetId = '0' THEN r.takerAssetId ELSE r.makerAssetId END
        JOIN sample s ON s.wallet = lower(r.maker) AND s.market = t.market
        WHERE CAST(r.timestamp AS BIGINT) >= epoch(CAST(? AS TIMESTAMPTZ))
          AND CAST(r.timestamp AS BIGINT) < epoch(CAST(? AS TIMESTAMPTZ))
        GROUP BY 1, 2, 3
    """, [window["lead_start"] + " 00:00:00+00", window["target_end"] + " 00:00:00+00"])

    con.execute("""
        CREATE OR REPLACE TEMP TABLE clean_blocks AS
        SELECT wallet, market, block, sum(CAST(round(dp * 1e6) AS HUGEINT)) AS units
        FROM (
            SELECT maker AS wallet, market, block, dp_maker AS dp FROM trades
            UNION ALL
            SELECT taker, market, block, -dp_maker FROM trades
        ) ledger JOIN sample USING (wallet, market)
        GROUP BY 1, 2, 3
    """)

    # Compare at block boundaries: maker legs and summary events may occur at
    # different log indices inside the same transaction. Comparing them at each
    # log index would incorrectly treat that temporary difference as an error.
    con.execute("""
        CREATE OR REPLACE TEMP TABLE compared AS
        WITH changes AS (
            SELECT wallet, market, block,
                coalesce(r.units, 0) AS raw_units,
                coalesce(c.units, 0) AS clean_units
            FROM raw_blocks r FULL JOIN clean_blocks c USING (wallet, market, block)
        )
        SELECT *,
            sum(raw_units) OVER w AS raw_position,
            sum(clean_units) OVER w AS clean_position
        FROM changes
        WINDOW w AS (PARTITION BY wallet, market ORDER BY block ROWS UNBOUNDED PRECEDING)
    """)
    summary = con.sql("""
        SELECT count(*) AS block_checkpoints,
            count(*) FILTER (WHERE raw_units <> clean_units) AS mismatched_changes,
            count(*) FILTER (WHERE raw_position <> clean_position) AS mismatched_positions,
            coalesce(max(abs(raw_position - clean_position)), 0) AS max_difference_microshares
        FROM compared
    """).fetchone()
    pairs = con.sql("""
        SELECT s.wallet, s.market, count(c.block) AS block_checkpoints,
            count(*) FILTER (WHERE c.raw_position <> c.clean_position) AS mismatched_positions
        FROM sample s LEFT JOIN compared c USING (wallet, market)
        GROUP BY 1, 2 ORDER BY 1, 2
    """).fetchall()
    checked = len(pairs)
    supported = sum(checkpoints > 0 for _, _, checkpoints, _ in pairs)
    passed = checked > 0 and supported == checked and summary[1] == summary[2] == 0
    return {
        "window": name,
        "passed": passed,
        "sampled_wallet_market_pairs": checked,
        "pairs_with_checkpoints": supported,
        "block_checkpoints": summary[0],
        "mismatched_changes": summary[1],
        "mismatched_positions": summary[2],
        "max_difference_microshares": summary[3],
        "sample": [
            {"wallet": wallet, "market": market, "block_checkpoints": checkpoints,
             "mismatched_positions": mismatches}
            for wallet, market, checkpoints, mismatches in pairs
        ],
        "mismatch_examples": con.sql("""
            SELECT wallet, market, block, raw_units, clean_units, raw_position, clean_position
            FROM compared WHERE raw_units <> clean_units OR raw_position <> clean_position
            ORDER BY wallet, market, block LIMIT 10
        """).df().to_dict("records"),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sample-size", type=int, default=100, help="Wallet-market pairs per weekly window")
    args = parser.parse_args()
    if args.sample_size < 1:
        parser.error("--sample-size must be positive")
    con = duckdb.connect()
    con.execute("SET threads = 4")
    con.execute("SET memory_limit = '4GB'")
    # Build the binary token map independently with explicit outcome indices.
    con.execute("""
        CREATE TEMP TABLE reference_tokens AS
        SELECT id AS market, positionIds[1] AS token, 1 AS sign FROM read_parquet(?)
        UNION ALL
        SELECT id, positionIds[2], -1 FROM read_parquet(?)
    """, [str(RAW / "condition.parquet")] * 2)
    reports = []
    for name, window in WEEKLY_WINDOWS.items():
        result = check_window(con, name, window, args.sample_size)
        reports.append(result)
        print(f"{'PASS' if result['passed'] else 'FAIL'} {name}: "
              f"{result['sampled_wallet_market_pairs']} pairs, "
              f"{result['block_checkpoints']} block checkpoints, "
              f"{result['mismatched_positions']} position mismatches", flush=True)

    output = {
        "all_passed": all(result["passed"] for result in reports),
        "windows_checked": len(reports),
        "sample_size_per_window": args.sample_size,
        "user_position_comparison": {
            "status": "incompatible_snapshot",
            "reason": "user_position is a per-user/token state table without historical timestamps; our windows end in 2024/2025.",
            "snapshot_cutoff": "2026-04-24T07:43:41+00:00",
            "state_reads_finished": "2026-04-24T08:20:06+00:00",
            "source": "https://huggingface.co/datasets/moose-code/polymarket-onchain-v1/blob/main/SNAPSHOT.json",
        },
        "limitations": [
            "Both ledgers use the same underlying fills and condition mapping; this is consistency validation, not independent ground truth.",
            "Both positions start at zero at the lead-in boundary; balances opened earlier are unknown.",
            "The sample is deterministic, not an estimate of population accuracy.",
            "Block-boundary agreement does not independently verify intra-block ordering or closure flags.",
            "Trade-derived net exposure is not a complete token-balance reconstruction including redemptions, transfers, and conversions.",
        ],
        "windows": reports,
    }
    RESULTS.mkdir(parents=True, exist_ok=True)
    out = RESULTS / "position_validation.json"
    out.write_text(json.dumps(output, indent=2) + "\n")
    print(f"Report: {out}")
    raise SystemExit(0 if output["all_passed"] else 1)


if __name__ == "__main__":
    main()

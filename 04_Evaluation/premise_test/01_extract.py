"""Step 1 (data pipeline; role A takes over in phase 2): raw fills -> one clean row per matched trade.

Why this is the hard part of pre-processing:
- Every on-chain fill is logged from the *maker's* point of view. The row's
  `taker` field is the real counterparty, except in the taker order's own
  summary row, where `taker` is the exchange contract. That summary row
  duplicates the maker rows, so we drop it.
- Amounts are strings in 6-decimal units (USDC and shares both), so we cast and divide by 1e6.
- Addresses mix upper/lower case, so we lowercase them.
- A token id says nothing about which market it belongs to. `condition.positionIds`
  maps each token to (market, outcome index 0 = "Yes", 1 = "No").

The trick that removes the need to rebuild the taker's side: in every match type
(buy/sell, buy/buy "mint", sell/sell "merge") one side ends up net long n shares
and the other net short n shares. So the taker's position change is always minus
the maker's, and each maker row counts n shares of volume (the paper's convention).

Run:  uv run python 04_Evaluation/premise_test/01_extract.py
"""

import json

import duckdb

from config import EXCHANGE_CONTRACTS, INTERIM, RAW, RESULTS, WINDOWS , WEEKLY_WINDOWS


def extract(con: duckdb.DuckDBPyConnection, name: str, w: dict) -> dict:
    files = [str(RAW / "order_filled" / f"{m}.parquet") for m in w["months"]]
    exchanges = ", ".join(f"'{a}'" for a in EXCHANGE_CONTRACTS)

    # Token -> (market, sign). sign = +1 for outcome 0 ("Yes"), -1 for outcome 1 ("No").
    con.execute(f"""
        CREATE OR REPLACE TEMP TABLE token_map AS
        SELECT token_id, market, CASE WHEN idx = 0 THEN 1 ELSE -1 END AS sign
        FROM (
            -- two unnests in one SELECT are zipped row-by-row in DuckDB
            SELECT id AS market,
                   unnest(positionIds) AS token_id,
                   unnest(range(len(positionIds))) AS idx
            FROM '{RAW / "condition.parquet"}'
        )
    """)

    con.execute(f"""
        CREATE OR REPLACE TEMP TABLE fills AS
        SELECT
            CAST(split_part(id, '_', 2) AS BIGINT) AS block,
            CAST(split_part(id, '_', 3) AS INTEGER) AS log_index,
            to_timestamp(CAST(timestamp AS BIGINT)) AS ts,
            lower(maker) AS maker,
            lower(taker) AS taker,
            makerAssetId = '0' AS maker_buys,
            CASE WHEN makerAssetId = '0' THEN takerAssetId ELSE makerAssetId END AS token_id,
            CASE WHEN makerAssetId = '0' THEN CAST(takerAmountFilled AS HUGEINT)
                 ELSE CAST(makerAmountFilled AS HUGEINT) END / 1e6 AS shares,
            CASE WHEN makerAssetId = '0' THEN CAST(makerAmountFilled AS HUGEINT)
                 ELSE CAST(takerAmountFilled AS HUGEINT) END / 1e6 AS usdc
        FROM read_parquet({files})
        WHERE to_timestamp(CAST(timestamp AS BIGINT)) >= TIMESTAMPTZ '{w["lead_start"]} 00:00:00+00'
          AND to_timestamp(CAST(timestamp AS BIGINT)) <  TIMESTAMPTZ '{w["target_end"]} 00:00:00+00'
    """)

    stats = {"window": name}
    stats["fill_rows"] = con.sql("SELECT count(*) FROM fills").fetchone()[0]
    stats["taker_summary_rows_dropped"] = con.sql(
        f"SELECT count(*) FROM fills WHERE taker IN ({exchanges})"
    ).fetchone()[0]

    out = INTERIM / f"{name}_trades.parquet"
    con.execute(f"""
        COPY (
            SELECT f.block, f.log_index, f.ts,
                   f.ts >= TIMESTAMPTZ '{w["target_start"]} 00:00:00+00' AS in_target,
                   t.market, f.maker, f.taker, f.shares, f.usdc,
                   -- maker's change in net long position; the taker's is the negative
                   (CASE WHEN f.maker_buys THEN 1 ELSE -1 END) * t.sign * f.shares AS dp_maker
            FROM fills f
            JOIN token_map t USING (token_id)
            WHERE f.taker NOT IN ({exchanges})
              AND f.maker <> f.taker
              AND f.shares > 0
        ) TO '{out}' (FORMAT parquet)
    """)

    # Sanity numbers that go straight into the Pre-processing slide
    stats["maker_rows"] = stats["fill_rows"] - stats["taker_summary_rows_dropped"]
    stats["unmapped_token_rows"] = con.sql(f"""
        SELECT count(*) FROM fills f ANTI JOIN token_map t USING (token_id)
        WHERE f.taker NOT IN ({exchanges})
    """).fetchone()[0]
    stats["self_trades"] = con.sql(
        f"SELECT count(*) FROM fills WHERE maker = taker AND taker NOT IN ({exchanges})"
    ).fetchone()[0]
    s = con.sql(f"""
        SELECT count(*), count(*) FILTER (in_target), sum(shares) FILTER (in_target),
               count(DISTINCT market) FILTER (in_target)
        FROM '{out}'
    """).fetchone()
    stats["trades_kept"], stats["target_trades"], stats["target_share_volume"], stats["target_markets"] = s
    return stats


def main() -> None:
    INTERIM.mkdir(parents=True, exist_ok=True)
    RESULTS.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    all_stats = []
    # Combine the two original baseline windows with the 18 weekly windows.
    # Each extraction writes its own Parquet file with history and target rows;
    # in_target distinguishes the target week from the historical lead-in.
    for name, w in (WINDOWS | WEEKLY_WINDOWS).items():
        st = extract(con, name, w)
        all_stats.append(st)
        print(json.dumps(st, indent=2, default=str))
    (RESULTS / "extract_stats.json").write_text(json.dumps(all_stats, indent=2, default=str))


if __name__ == "__main__":
    main()

"""Compare 30/90/180-day histories while keeping target weeks and Algorithm 1 fixed.

Run from the repository root:
    uv run python 04_Evaluation/premise_test/05_leadin_sensitivity.py --plan
    uv run python 04_Evaluation/premise_test/05_leadin_sensitivity.py --download-only
    uv run python 04_Evaluation/premise_test/05_leadin_sensitivity.py

Original baseline and weekly datasets/results are preserved. A 30-day June
history starts May 2, unlike the calendar-month baseline starting May 1.
"""

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
import importlib.util
import json
from pathlib import Path
import subprocess
import time

import duckdb
import pyarrow.parquet as pq

from config import C_CLOSURE, INTERIM, RAW, RESULTS, THETA, TOL, WINDOWS


OUTPUT = RESULTS / "lead_in"
SCORES = INTERIM / "lead_in_scores"
BASE_URL = "https://huggingface.co/datasets/moose-code/polymarket-onchain-v1/resolve/main"


def load_script(filename: str):
    """Reuse existing extraction and scoring; do not reimplement Algorithm 1."""
    spec = importlib.util.spec_from_file_location(filename[:-3], Path(__file__).with_name(filename))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def experiment_windows(days: list[int]) -> dict:
    windows = {}
    for period, baseline in WINDOWS.items():
        start = date.fromisoformat(baseline["target_start"])
        end = date.fromisoformat(baseline["target_end"])
        for length in days:
            lead = start - timedelta(days=length)
            month = lead.replace(day=1)
            months = []
            while month < end:
                months.append(month.strftime("%Y-%m"))
                month = date(month.year + 1, 1, 1) if month.month == 12 else date(month.year, month.month + 1, 1)
            windows[f"{period}_lead{length:03d}"] = {
                "period": period, "lead_days": length, "months": months,
                "lead_start": lead.isoformat(), "target_start": start.isoformat(),
                "target_end": end.isoformat(),
            }
    return windows


def valid_parquet(path: Path) -> bool:
    if not path.exists():
        return False
    try:
        pq.read_metadata(path)
        return True
    except (OSError, ValueError):
        return False


def download_month(month: str) -> None:
    """Resume on each retry, and publish the final filename only after metadata checks."""
    target = RAW / "order_filled" / f"{month}.parquet"
    if valid_parquet(target):
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_suffix(".parquet.part")
    year, number = month.split("-")
    url = f"{BASE_URL}/order_filled/year={year}/month={number}.parquet"
    for attempt in range(1, 11):
        print(f"Downloading {month}, attempt {attempt}", flush=True)
        result = subprocess.run([
            "curl", "-fL", "-sS", "-C", "-", "--connect-timeout", "30",
            "--speed-time", "60", "--speed-limit", "1024", "-o", str(partial), url,
        ])
        if result.returncode == 0 and valid_parquet(partial):
            partial.replace(target)
            print(f"Downloaded {month}: {target.stat().st_size:,} bytes", flush=True)
            return
        time.sleep(5)
    raise RuntimeError(f"Download failed for {month}; partial file retained at {partial}")


def compare_scores(con, period: str, left: dict, right: dict) -> dict:
    """Compare the same target wallets and trades, rather than changing populations."""
    a, b = left["window"], right["window"]
    con.read_parquet(str(SCORES / f"{a}.parquet")).create_view("left_scores", replace=True)
    con.read_parquet(str(SCORES / f"{b}.parquet")).create_view("right_scores", replace=True)
    con.read_parquet(str(INTERIM / f"{a}_trades.parquet")).create_view("left_trades", replace=True)
    con.read_parquet(str(INTERIM / f"{b}_trades.parquet")).create_view("right_trades", replace=True)
    # Verify both extractions contain identical target events and trade values.
    different = con.sql("""
        SELECT count(*) FROM (
            (SELECT * FROM left_trades WHERE in_target
             EXCEPT ALL SELECT * FROM right_trades WHERE in_target)
            UNION ALL
            (SELECT * FROM right_trades WHERE in_target
             EXCEPT ALL SELECT * FROM left_trades WHERE in_target)
        )
    """).fetchone()[0]
    if different:
        raise RuntimeError(f"Target trades changed between {a} and {b}: {different} rows")
    wallets = con.execute("""
        SELECT count(*), avg(abs(l.x-r.x)), max(abs(l.x-r.x)),
            count(*) FILTER (WHERE (l.x >= ?) <> (r.x >= ?))
        FROM left_scores l JOIN right_scores r USING(wallet)
    """, [THETA, THETA]).fetchone()
    totals = [con.sql(f"SELECT count(*) FROM {table}").fetchone()[0]
              for table in ("left_scores", "right_scores")]
    if wallets[0] == 0 or totals != [wallets[0], wallets[0]]:
        raise RuntimeError(f"Target wallet populations differ between {a} and {b}")
    trades = con.execute("""
        SELECT count(*), sum(t.shares),
            count(*) FILTER (WHERE (least(a.x,b.x) >= ?) <> (least(c.x,d.x) >= ?)),
            coalesce(sum(t.shares) FILTER (
                WHERE (least(a.x,b.x) >= ?) <> (least(c.x,d.x) >= ?)), 0)
        FROM left_trades t
        JOIN left_scores a ON a.wallet=t.maker JOIN left_scores b ON b.wallet=t.taker
        JOIN right_scores c ON c.wallet=t.maker JOIN right_scores d ON d.wallet=t.taker
        WHERE t.in_target
    """, [THETA] * 4).fetchone()
    left_frac = left["algorithm"]["target_wash_share_volume"] / left["algorithm"]["target_share_volume"]
    right_frac = right["algorithm"]["target_wash_share_volume"] / right["algorithm"]["target_share_volume"]
    return {
        "period": period, "from_days": left["lead_days"], "to_days": right["lead_days"],
        "identical_target_trades": True, "target_wallets_compared": wallets[0],
        "mean_absolute_score_change": wallets[1], "max_absolute_score_change": wallets[2],
        "wallet_threshold_crossings": wallets[3],
        "wallet_threshold_crossing_fraction": wallets[3] / wallets[0],
        "target_trades": trades[0], "changed_trade_flags": trades[2],
        "changed_flag_share_volume": trades[3],
        "changed_flag_volume_fraction": trades[3] / trades[1],
        "flagged_volume_change_percentage_points": 100 * (right_frac - left_frac),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, nargs="+", default=[30, 90, 180])
    parser.add_argument("--periods", nargs="+", choices=list(WINDOWS), default=list(WINDOWS))
    parser.add_argument("--plan", action="store_true", help="List windows and missing months only")
    parser.add_argument("--download-only", action="store_true", help="Download missing monthly fills, then stop")
    parser.add_argument("--compare-only", action="store_true", help="Compare saved runs without repeating extraction/scoring")
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--memory-limit", default="8GB")
    args = parser.parse_args()
    if min(args.days) < 1 or args.threads < 1:
        parser.error("Days and threads must be positive")
    windows = {name: window for name, window in experiment_windows(sorted(set(args.days))).items()
               if window["period"] in args.periods}
    months = sorted({month for window in windows.values() for month in window["months"]})
    missing = [month for month in months if not valid_parquet(RAW / "order_filled" / f"{month}.parquet")]
    plan = {"windows": windows, "missing_months": missing}
    if args.plan:
        print(json.dumps(plan, indent=2))
        return
    if args.download_only:
        with ThreadPoolExecutor(max_workers=3) as pool:
            list(pool.map(download_month, missing))
        return
    if missing and not args.compare_only:
        parser.error(f"Missing monthly files: {', '.join(missing)}. Run --download-only first.")

    extract = load_script("01_extract.py").extract
    score = load_script("02_alg1.py").run_window
    OUTPUT.mkdir(parents=True, exist_ok=True)
    SCORES.mkdir(parents=True, exist_ok=True)
    records = []
    for name, window in windows.items():
        if args.compare_only:
            record = json.loads((OUTPUT / f"{name}.json").read_text())
            expected = {"theta": THETA, "closure": C_CLOSURE, "tolerance": TOL}
            if record["parameters"] != expected or any(record[key] != value for key, value in window.items()):
                raise RuntimeError(f"Saved settings for {name} differ from the current experiment")
            records.append(record)
            continue
        # A separate connection per run releases historical ledger tables before
        # the next run. DuckDB can spill larger windows to the task's temp folder.
        con = duckdb.connect()
        con.execute("SET threads = ?", [args.threads])
        con.execute("SET memory_limit = ?", [args.memory_limit])
        con.execute("SET temp_directory = ?", [str(INTERIM / "lead_in_temp")])
        print(f"Running {name}: {window['lead_start']} to {window['target_end']}", flush=True)
        stats = extract(con, name, window)
        algorithm = score(con, name)
        # run_window registers the final score table; save only wallets that trade
        # in the fixed target week so comparisons use the same population.
        con.read_parquet(str(INTERIM / f"{name}_trades.parquet")).create_view("target_trades", replace=True)
        target_scores = con.sql("""
            SELECT wallet, x FROM score WHERE wallet IN (
                SELECT maker FROM target_trades WHERE in_target
                UNION SELECT taker FROM target_trades WHERE in_target
            ) ORDER BY wallet
        """)
        target_scores.write_parquet(str(SCORES / f"{name}.parquet"))
        # Metadata coverage is a separate diagnostic: a market whose reported
        # start date precedes the lead-in may have unobserved opening positions.
        # Aggregate outcome-token metadata before joining to avoid doubling volume.
        con.read_parquet(str(RAW / "market_data.parquet")).create_view("market_metadata", replace=True)
        coverage = con.execute("""
            WITH target_volume AS (
                SELECT market, sum(shares) AS volume FROM target_trades
                WHERE in_target GROUP BY market
            ), starts AS (
                SELECT condition AS market, min(try_cast(startDate AS TIMESTAMPTZ)) AS opened
                FROM market_metadata GROUP BY condition
            )
            SELECT count(*),
                count(*) FILTER (WHERE opened IS NULL),
                coalesce(sum(volume) FILTER (WHERE opened IS NULL), 0) / sum(volume),
                coalesce(sum(volume) FILTER (WHERE opened >= CAST(? AS TIMESTAMPTZ)
                    AND opened < CAST(? AS TIMESTAMPTZ)), 0) / sum(volume)
            FROM target_volume LEFT JOIN starts USING(market)
        """, [window["lead_start"] + " 00:00:00+00", window["target_end"] + " 00:00:00+00"]).fetchone()
        record = {"window": name, **window, "extraction": stats, "algorithm": algorithm,
                  "parameters": {"theta": THETA, "closure": C_CLOSURE, "tolerance": TOL},
                  "metadata_history_coverage": {
                      "target_markets": coverage[0], "markets_without_start_date": coverage[1],
                      "volume_fraction_without_start_date": coverage[2],
                      "volume_fraction_with_market_start_inside_history": coverage[3],
                      "limitation": "Reported market start dates are a coverage proxy, not proof of complete on-chain history.",
                  }}
        (OUTPUT / f"{name}.json").write_text(json.dumps(record, indent=2) + "\n")
        records.append(record)
        print(f"Finished {name}: flagged {algorithm['wash_fraction_theta_0.9']:.2%}", flush=True)
        con.close()

    comparisons = []
    with duckdb.connect() as con:
        con.execute("SET threads = ?", [args.threads])
        con.execute("SET memory_limit = ?", [args.memory_limit])
        con.execute("SET temp_directory = ?", [str(INTERIM / "lead_in_temp")])
        for period in dict.fromkeys(args.periods):
            runs = [record for record in records if record["period"] == period]
            for i, left in enumerate(runs):
                for right in runs[i+1:]:
                    comparisons.append(compare_scores(con, period, left, right))
    report = {
        "days": sorted(set(args.days)), "periods": list(dict.fromkeys(args.periods)),
        "runs": records, "comparisons": comparisons,
        "limitations": [
            "Changing history changes both closure evidence and the counterparty network; this is lead-in sensitivity, not a positions-only experiment.",
            "Longer history does not supply ground truth or guarantee complete starting balances.",
            "A 30-day June history starts May 2; the original baseline starts May 1.",
        ],
    }
    # Include the chosen lengths in the report name so partial 30-day runs do not
    # overwrite a completed three-length comparison.
    prefix = "" if set(args.periods) == set(WINDOWS) else "_".join(report["periods"]) + "_"
    out = OUTPUT / (prefix + "sensitivity_" + "_".join(str(day) for day in report["days"]) + ".json")
    out.write_text(json.dumps(report, indent=2) + "\n")
    print(f"Report: {out}")


if __name__ == "__main__":
    main()

"""Check weekly extraction outputs without modifying the trade datasets.

Run from the repository root:
    uv run python 04_Evaluation/premise_test/03_validate.py

These checks cover dataset integrity. They do not independently validate token
mapping, reconstructed positions, or whether a trade is wash trading.
"""

import json
import math

import duckdb

from config import EXCHANGE_CONTRACTS, INTERIM, RESULTS, WEEKLY_WINDOWS


def main() -> None:
    con = duckdb.connect()
    con.execute("SET threads = 4")
    con.execute("SET memory_limit = '4GB'")
    stats = {
        row["window"]: row
        for row in json.loads((RESULTS / "extract_stats.json").read_text())
    }
    reports = []

    for name, window in WEEKLY_WINDOWS.items():
        path = INTERIM / f"{name}_trades.parquet"
        if not path.exists():
            reports.append({"window": name, "passed": False, "error": "Missing file"})
            print(f"FAIL {name}: missing file", flush=True)
            continue

        try:
            con.read_parquet(str(path)).create_view("trades", replace=True)
            # Explicit UTC boundaries match the extraction script. Dates at
            # target_end belong to the next window, not the current target week.
            row = con.execute(
                """
                SELECT count(*) AS rows,
                    count(*) FILTER (WHERE in_target) AS target_rows,
                    coalesce(sum(shares) FILTER (WHERE in_target), 0) AS target_shares,
                    count(*) - count(DISTINCT (block, log_index)) AS duplicate_events,
                    count(*) FILTER (WHERE
                        block IS NULL OR log_index IS NULL OR ts IS NULL OR
                        in_target IS NULL OR market IS NULL OR maker IS NULL OR
                        taker IS NULL OR shares IS NULL OR usdc IS NULL OR dp_maker IS NULL
                    ) AS null_rows,
                    count(*) FILTER (WHERE ts < CAST(? AS TIMESTAMPTZ)
                        OR ts >= CAST(? AS TIMESTAMPTZ)) AS outside_window,
                    count(*) FILTER (WHERE in_target IS DISTINCT FROM
                        (ts >= CAST(? AS TIMESTAMPTZ) AND ts < CAST(? AS TIMESTAMPTZ))
                    ) AS incorrect_target_flags,
                    count(*) FILTER (WHERE NOT isfinite(shares) OR shares <= 0
                        OR NOT isfinite(usdc) OR usdc < 0) AS invalid_amounts,
                    count(*) FILTER (WHERE NOT isfinite(dp_maker)
                        OR abs(abs(dp_maker) - shares) > 1e-8) AS invalid_position_changes,
                    count(*) FILTER (WHERE maker = taker) AS self_trades,
                    count(*) FILTER (WHERE maker <> lower(maker)
                        OR taker <> lower(taker)) AS mixed_case_addresses,
                    count(*) FILTER (WHERE taker IN (?, ?)) AS exchange_summary_rows,
                    count(*) FILTER (WHERE shares > 0 AND usdc / shares > 1 + 1e-8
                    ) AS prices_above_one
                FROM trades
                """,
                [
                    window["lead_start"] + " 00:00:00+00",
                    window["target_end"] + " 00:00:00+00",
                    window["target_start"] + " 00:00:00+00",
                    window["target_end"] + " 00:00:00+00",
                    *EXCHANGE_CONTRACTS,
                ],
            ).fetchone()
            names = [column[0] for column in con.description]
            metrics = dict(zip(names, row))

            # Compare independently read output counts with the saved extraction
            # summary. Overlapping lead-in rows are expected across different files.
            saved = stats.get(name)
            checks = {
                key: metrics[key] == 0
                for key in names[3:-1]
            }
            checks["nonempty_target"] = metrics["target_rows"] > 0
            checks["matches_extraction_stats"] = saved is not None and (
                metrics["rows"] == saved["trades_kept"]
                and metrics["target_rows"] == saved["target_trades"]
                and math.isclose(metrics["target_shares"], saved["target_share_volume"], rel_tol=1e-9)
            )
            passed = all(checks.values())
            reports.append({"window": name, "passed": passed, "checks": checks, "metrics": metrics})
            failed = [key for key, ok in checks.items() if not ok]
            print(f"{'PASS' if passed else 'FAIL'} {name}: {metrics['target_rows']:,} target trades"
                  + (f"; failed checks: {', '.join(failed)}" if failed else ""), flush=True)
        except duckdb.Error as error:
            reports.append({"window": name, "passed": False, "error": str(error)})
            print(f"FAIL {name}: {error}", flush=True)

    output = {
        "all_passed": all(report["passed"] for report in reports),
        "windows_checked": len(reports),
        "windows": reports,
        "limitations": [
            "Position-change magnitudes are checked, but outcome signs and historical positions need independent validation.",
            "Prices above one are recorded for investigation, not treated as automatic failures.",
            "Passing integrity checks does not confirm wash-trading labels.",
        ],
    }
    out = RESULTS / "weekly_validation.json"
    out.write_text(json.dumps(output, indent=2) + "\n")
    print(f"Report: {out}")
    raise SystemExit(0 if output["all_passed"] else 1)


if __name__ == "__main__":
    main()

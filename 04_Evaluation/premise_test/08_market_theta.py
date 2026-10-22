"""Step 8 (evaluation; role B): per-market theta-sensitivity + the Trump case study.

The premise test reports one wash fraction per window at the fixed theta = 0.9.
That hides a question the examiner will ask: *is a specific flagged market real
wash, or a false positive?* The headline example is the "Will Donald Trump be
inaugurated?" market, which our fixed-theta run flags ~89%, yet the paper's
Algorithm 2 flags nothing there.

This step answers it with evidence instead of assertion. For every market it
computes the flagged share of target-week volume across a grid of thresholds. A
genuine-wash market (sports long-shots) stays flagged as theta rises toward 0.99,
because its wallets score ~1. A false positive is flagged only near theta = 0.9 and
collapses by 0.99, because its "wash" rests on wallets sitting just over the line.
The ratio wash(0.99) / wash(0.90) is that robustness in one number.

Outputs (per window):
  results/market_theta/<window>.parquet   full per-market theta curves
  results/market_theta/case_study.json    Trump market vs the most robust markets
  results/market_theta/trump_case_study.png   the theta curves, slide-ready

Run:  uv run python 04_Evaluation/premise_test/08_market_theta.py
"""

import importlib.util
import json
from pathlib import Path

import duckdb
import matplotlib
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from config import RAW, RESULTS, THETA, WINDOWS  # noqa: E402

_ALG1 = Path(__file__).resolve().parent / "02_alg1.py"
_spec = importlib.util.spec_from_file_location("alg1", _ALG1)
alg1 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(alg1)

THETAS = [0.70, 0.80, 0.90, 0.95, 0.99]
CASE_STUDY_WINDOW = "dec2024"            # the window the Trump market lives in
MARKETS = str(RAW / "market_data.parquet")
# A market counts as "robust wash" if it stays mostly flagged at the strictest theta.
ROBUST_MIN_FRAC = 0.5                    # wash(0.99) >= this share of wash(0.90)


def market_theta(con: duckdb.DuckDBPyConnection, name: str, w: dict) -> pd.DataFrame:
    trades = str(alg1.INTERIM / f"{name}_trades.parquet")
    s = alg1.score_wallets(con, trades)
    con.register("score", pd.DataFrame({"wallet": s["wallets"], "x": s["x"]}))

    frac_cols = ",\n".join(
        f'sum(shares) FILTER (minscore >= {th}) / sum(shares) AS "wf_{th:.2f}"' for th in THETAS
    )
    df = con.sql(f"""
        WITH t AS (SELECT * FROM '{trades}' WHERE in_target),
        scored AS (
            SELECT t.market, t.maker, t.taker, t.shares, least(a.x, b.x) AS minscore
            FROM t JOIN score a ON a.wallet = t.maker
                   JOIN score b ON b.wallet = t.taker
        ),
        md AS (
            SELECT condition,
                   any_value(marketName) AS name,
                   lower(coalesce(any_value(marketName), '') || ' ' ||
                         coalesce(any_value(marketSlug), '')) AS txt,
                   min(startDate) AS start_date
            FROM '{MARKETS}' GROUP BY condition
        )
        SELECT scored.market,
               md.name, md.start_date,
               '{w["lead_start"]}' AS lead_start,
               coalesce(md.start_date >= '{w["lead_start"]}', false) AS opened_in_window,
               sum(shares) AS target_vol,
               {frac_cols}
        FROM scored LEFT JOIN md ON md.condition = scored.market
        GROUP BY scored.market, md.name, md.start_date
        ORDER BY target_vol DESC
    """).df()

    # A market with no trades surviving a threshold has 0 flagged there, not NULL.
    for c in [f"wf_{th:.2f}" for th in THETAS]:
        df[c] = df[c].fillna(0.0).round(4)
    # One-number robustness: how much of the theta=0.9 flag survives to theta=0.99.
    f90, f99 = df["wf_0.90"], df["wf_0.99"]
    df["robustness"] = (f99 / f90.where(f90 > 0)).fillna(0.0).round(4)
    df["robust_wash"] = (f90 >= 0.5) & (df["robustness"] >= ROBUST_MIN_FRAC)
    return df


def build_case_study(df: pd.DataFrame) -> dict:
    """Pull the Trump-inauguration market and contrast it with the robust markets."""
    name_txt = df["name"].fillna("").str.lower()
    trump = df[name_txt.str.contains("trump") & name_txt.str.contains("inaugurat")]
    if len(trump) == 0:  # fall back to any Trump market, else empty
        trump = df[name_txt.str.contains("trump")]

    curve_cols = ["market", "name", "target_vol", *[f"wf_{th:.2f}" for th in THETAS],
                  "robustness", "robust_wash", "opened_in_window", "start_date", "lead_start"]

    def rows(frame):
        return json.loads(frame[curve_cols].to_json(orient="records", date_format="iso"))

    # The most robust large markets (genuine wash) for side-by-side contrast.
    robust = df[df["robust_wash"]].nlargest(5, "target_vol")
    verdict = {}
    if len(trump):
        t = trump.nlargest(1, "target_vol").iloc[0]
        verdict = {
            "market_name": t["name"],
            "flagged_at_theta_0.90": float(t["wf_0.90"] or 0),
            "flagged_at_theta_0.99": float(t["wf_0.99"] or 0),
            "robustness_0.99_over_0.90": float(t["robustness"]),
            "robust_wash": bool(t["robust_wash"]),
            "opened_inside_window_leadin": bool(t["opened_in_window"]),
            "reading": (
                "flagged at the fixed theta but the flag is NOT robust: it collapses as "
                "theta rises, unlike genuine-wash markets -> treat as a false-positive case study"
                if not bool(t["robust_wash"]) else
                "flag is robust across theta, so this is not a clear false positive"
            ),
        }
    return {"thetas": THETAS, "trump_market": rows(trump), "robust_markets": rows(robust),
            "verdict": verdict}


def plot_case_study(case: dict, out: Path) -> None:
    fig, ax = plt.subplots(figsize=(7, 3.8))
    for m in case["robust_markets"][:3]:
        ax.plot(THETAS, [m[f"wf_{th:.2f}"] or 0 for th in THETAS],
                color="#5B6B7A", lw=1.4, marker="o", ms=3, alpha=0.8,
                label=f"{(m['name'] or m['market'])[:28]} (robust)")
    for m in case["trump_market"][:1]:
        ax.plot(THETAS, [m[f"wf_{th:.2f}"] or 0 for th in THETAS],
                color="#D55E00", lw=2.4, marker="o", ms=5,
                label=f"{(m['name'] or m['market'])[:28]} (Trump)")
    ax.axvline(THETA, color="#1A2733", ls="--", lw=1, alpha=0.6)
    ax.set(xlabel="threshold θ", ylabel="flagged share of market volume",
           ylim=(0, 1.02), title="Per-market θ-sensitivity: Trump market vs robust-wash markets")
    ax.grid(alpha=0.25)
    ax.legend(frameon=False, fontsize=7, loc="lower left")
    fig.tight_layout()
    fig.savefig(out, dpi=150, bbox_inches="tight")


def main() -> None:
    out_dir = RESULTS / "market_theta"
    out_dir.mkdir(parents=True, exist_ok=True)
    with duckdb.connect() as con:
        curves = {}
        for name, w in WINDOWS.items():
            df = market_theta(con, name, w)
            df.to_parquet(out_dir / f"{name}.parquet")
            curves[name] = df
            print(f"{name}: {len(df)} markets · "
                  f"{int(df['robust_wash'].sum())} robust-wash · "
                  f"flagged vol@θ0.9 "
                  f"{100 * (df['target_vol'] * df['wf_0.90'].fillna(0)).sum() / df['target_vol'].sum():.1f}%")

    case = build_case_study(curves[CASE_STUDY_WINDOW])
    (out_dir / "case_study.json").write_text(json.dumps(case, indent=2, default=float))
    plot_case_study(case, out_dir / "trump_case_study.png")
    print("\ncase study verdict:", json.dumps(case["verdict"], indent=2, default=float))


if __name__ == "__main__":
    main()

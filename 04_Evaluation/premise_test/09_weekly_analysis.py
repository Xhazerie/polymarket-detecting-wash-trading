"""Score the 18 non-overlapping target weeks using their existing 30-day histories.

Run from the repository root:
    uv run python 04_Evaluation/premise_test/09_weekly_analysis.py

One scoring pass per window is shared by wallet flags, market theta curves and EDA.
Outputs are isolated in results/weekly/. No baseline outputs are overwritten.
Summaries and CSVs are reviewable; large wallet/market parquet files stay gitignored.
"""

import argparse
import importlib.util
import json
import math
from datetime import date
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from config import INTERIM, RAW, RESULTS, THETA, TOL, WEEKLY_LEAD_DAYS, WEEKLY_WINDOWS


def load_script(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(filename))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


alg = load_script('weekly_alg', '02_alg1.py')
flags = load_script('weekly_flags', '07_wallet_flags.py')
theta = load_script('weekly_theta', '08_market_theta.py')
OUT = RESULTS / 'weekly'

# Same keyword rules/order as eda_round2.ipynb. These are heuristic categories.
CATEGORY_SQL = r"""
    SELECT condition AS market, name,
        CASE
        WHEN regexp_matches(txt, '\b(bitcoin|btc|eth|ethereum|solana|sol|xrp|crypto|memecoin|token|airdrop|binance|coinbase|usdc|usdt|pepe)\b') THEN 'Crypto'
        WHEN regexp_matches(txt, '\b(nba|nfl|nhl|mlb|ncaa|ufc|mma|super bowl|stanley cup|premier league|champions league|uefa|fifa|f1|grand prix|playoffs?|finals?|championship|tennis|golf|boxing|fight|vs\.?|world series|olympics?)\b') THEN 'Sports'
        WHEN regexp_matches(txt, '\b(fed|interest rates?|inflation|cpi|gdp|recession|unemployment|tariffs?|s&p|nasdaq|stocks?|treasury|gold|oil)\b') THEN 'Economy'
        WHEN regexp_matches(txt, '\b(trump|biden|harris|election|elected|president|senate|house|governor|primary|democrat\w*|republican\w*|votes?|inaugurated|ceasefire|war|nato|ukraine|russia|israel|gaza|iran)\b') THEN 'Politics'
        ELSE 'Other' END AS category
    FROM (
        SELECT condition, any_value(marketName) AS name,
               lower(coalesce(any_value(marketName), '') || ' ' || coalesce(any_value(marketSlug), '')) AS txt
        FROM '{markets}' GROUP BY condition
    )
"""


def save_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')


def analyse_window(con, name: str, w: dict, expected: dict) -> dict:
    trades = INTERIM / f'{name}_trades.parquet'
    scores = alg.score_wallets(con, str(trades))
    assert scores['converged'], (name, 'did not converge')
    assert np.isfinite(scores['x']).all() and np.isfinite(scores['x0']).all()
    assert ((scores['x'] >= -1e-10) & (scores['x'] <= 1 + 1e-10)).all()
    mean0 = float(scores['deg'] @ scores['x0'] / scores['deg'].sum())
    meanx = float(scores['deg'] @ scores['x'] / scores['deg'].sum())
    iterations = int(scores['iterations'])
    relative_change = scores['relative_change']
    assert abs(mean0 - meanx) < TOL, (name, 'weighted score not conserved')
    con.execute('DROP TABLE ledger')
    con.execute('DROP TABLE wm')

    wallet_summary = flags.wallet_flags(con, name, OUT / 'wallet_flags', scores=scores)
    markets = theta.market_theta(con, name, w, scores=scores)
    markets.to_parquet(OUT / 'market_theta' / f'{name}.parquet')
    del scores
    fpath = OUT / 'wallet_flags' / f'{name}.parquet'
    con.execute(f"CREATE OR REPLACE TEMP VIEW wf AS SELECT * FROM '{fpath}'")
    con.execute(f"""
        CREATE OR REPLACE TEMP TABLE target AS
        SELECT t.*, least(a.x, b.x) AS minscore,
               least(a.x, b.x) >= {THETA} AS flagged_trade,
               coalesce(md.category, 'Other') AS category
        FROM '{trades}' t
        JOIN score a ON a.wallet = t.maker
        JOIN score b ON b.wallet = t.taker
        LEFT JOIN categories md USING (market)
        WHERE t.in_target
    """)
    basic = con.sql("""
        SELECT count(*) AS target_trades, count(DISTINCT market) AS target_markets,
               sum(shares) AS share_volume, sum(usdc) AS usdc_volume,
               coalesce(sum(shares) FILTER (flagged_trade), 0) AS flagged_share_volume,
               coalesce(sum(usdc) FILTER (flagged_trade), 0) AS flagged_usdc_volume,
               min(ts) AS first_trade, max(ts) AS last_trade
        FROM target
    """).df().iloc[0]
    assert int(basic.target_trades) == expected['target_trades'], name
    assert int(basic.target_markets) == expected['target_markets'], name
    assert math.isclose(basic.share_volume, expected['target_share_volume'], rel_tol=1e-9), name
    assert math.isclose(basic.flagged_share_volume, wallet_summary['target_wash_share_volume'], rel_tol=1e-9), name
    assert pd.Timestamp(w['target_start'], tz='UTC') <= basic.first_trade
    assert basic.last_trade < pd.Timestamp(w['target_end'], tz='UTC')

    fractions = {f'{t:.2f}': float(con.sql(
        f'SELECT coalesce(sum(shares) FILTER (minscore >= {t}), 0) / sum(shares) FROM target'
    ).fetchone()[0]) for t in theta.THETAS}
    assert all(a >= b for a, b in zip(fractions.values(), list(fractions.values())[1:]))
    for t in theta.THETAS:
        got = float(np.average(markets[f'wf_{t:.2f}'], weights=markets.target_vol))
        assert abs(got - fractions[f'{t:.2f}']) <= 5.1e-5, (name, 'market theta mismatch')

    wallet_checks = con.sql(f"""
        SELECT count(*) = count(DISTINCT wallet),
               bool_and(flagged = (x >= {THETA})),
               bool_and(in_wash_trade = (target_wash_vol > 0)),
               bool_and(target_wash_vol <= target_vol + 1e-6),
               sum(target_vol) / 2, sum(target_wash_vol) / 2
        FROM wf
    """).fetchone()
    assert all(wallet_checks[:4]), name
    assert math.isclose(wallet_checks[4], basic.share_volume, rel_tol=1e-9), name
    assert math.isclose(wallet_checks[5], basic.flagged_share_volume, rel_tol=1e-9), name

    con.execute("""
        CREATE OR REPLACE TEMP TABLE edges AS
        SELECT wallet, partner, sum(shares) AS v FROM (
            SELECT maker AS wallet, taker AS partner, shares FROM target
            UNION ALL SELECT taker, maker, shares FROM target
        ) GROUP BY 1, 2
    """)
    profile = con.sql("""
        WITH ranked AS (
            SELECT *, row_number() OVER (PARTITION BY wallet ORDER BY v DESC) AS rk FROM edges
        ), p AS (
            SELECT wallet, max(v) / sum(v) AS top1,
                   sum(v) FILTER (rk <= 2) / sum(v) AS top2
            FROM ranked GROUP BY wallet
        )
        SELECT f.flagged, count(*) AS wallets, sum(f.target_vol) AS endpoint_volume,
               sum(p.top1 * f.target_vol) / sum(f.target_vol) AS top1_share,
               sum(p.top2 * f.target_vol) / sum(f.target_vol) AS top2_share,
               median(f.n_counterparties) AS median_partners, median(f.n_markets) AS median_markets
        FROM wf f JOIN p USING (wallet) GROUP BY flagged ORDER BY flagged
    """).df()
    active = int(profile.wallets.sum())
    active_flagged = int(profile.loc[profile.flagged, 'wallets'].sum())
    assort = con.sql("""
        WITH a AS (
            SELECT e.wallet, sum(e.v) AS vol,
                   coalesce(sum(e.v) FILTER (p.flagged), 0) / sum(e.v) AS frac
            FROM edges e JOIN wf f ON f.wallet = e.wallet
                         JOIN wf p ON p.wallet = e.partner
            WHERE f.flagged GROUP BY e.wallet
        ) SELECT coalesce(median(frac), 0),
                 coalesce(sum(vol) FILTER (frac >= 0.9), 0), coalesce(sum(vol), 0) FROM a
    """).fetchone()
    categories = con.sql("""
        SELECT category, sum(shares) AS share_volume,
               coalesce(sum(shares) FILTER (flagged_trade), 0) AS flagged_share_volume,
               coalesce(sum(shares) FILTER (flagged_trade AND usdc / shares < 0.02), 0) AS flagged_lowprice_share_volume
        FROM target GROUP BY category ORDER BY category
    """).df()
    daily = con.sql("""
        SELECT CAST(ts AS DATE) AS date, count(*) AS trades, sum(shares) AS share_volume,
               coalesce(sum(shares) FILTER (flagged_trade), 0) AS flagged_share_volume,
               sum(usdc) AS usdc_volume
        FROM target GROUP BY 1 ORDER BY 1
    """).df()
    daily.to_csv(OUT / 'daily' / f'{name}.csv', index=False)
    days = (date.fromisoformat(w['target_end']) - date.fromisoformat(w['target_start'])).days
    assert len(daily) == days, (name, 'missing target dates')
    assert math.isclose(daily.share_volume.sum(), basic.share_volume, rel_tol=1e-9)
    period = 'Nov-Dec 2024' if w['target_start'].startswith('2024') else 'May-Jun 2025'
    return {
        'window': name, 'period': period, 'lead_start': w['lead_start'],
        'target_start': w['target_start'], 'target_end_exclusive': w['target_end'], 'target_days': days,
        'lead_days': WEEKLY_LEAD_DAYS, 'target_trades': int(basic.target_trades),
        'target_markets': int(basic.target_markets), 'active_wallets': active,
        'active_flagged_wallets': active_flagged, 'active_flagged_wallet_fraction': active_flagged / active,
        'share_volume': float(basic.share_volume), 'usdc_volume': float(basic.usdc_volume),
        'share_volume_per_day': float(basic.share_volume / days),
        'flagged_share_volume': float(basic.flagged_share_volume),
        'flagged_usdc_volume': float(basic.flagged_usdc_volume),
        'flagged_share_fraction': fractions['0.90'],
        'flagged_usdc_fraction': float(basic.flagged_usdc_volume / basic.usdc_volume),
        'theta_fractions': fractions, 'wallets_including_leadin': wallet_summary['wallets'],
        'iterations': iterations, 'relative_change': relative_change, 'converged': True,
        'weighted_score_x0': mean0, 'weighted_score_final': meanx,
        'robust_flag_markets': int(markets.robust_wash.sum()),
        'profile': profile.to_dict(orient='records'), 'categories': categories.to_dict(orient='records'),
        'flagged_wallet_median_partner_flagged_fraction': float(assort[0]),
        'flagged_endpoint_volume_mostly_with_flagged': float(assort[1]),
        'flagged_endpoint_volume': float(assort[2]),
        'validation': 'passed',
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--windows', nargs='+', choices=list(WEEKLY_WINDOWS), default=list(WEEKLY_WINDOWS))
    parser.add_argument('--threads', type=int, default=8)
    args = parser.parse_args()
    for sub in ['wallet_flags', 'market_theta', 'windows', 'daily']:
        (OUT / sub).mkdir(parents=True, exist_ok=True)
    expected = {r['window']: r for r in json.loads((RESULTS / 'extract_stats.json').read_text())}
    for name in args.windows:
        if not (INTERIM / f'{name}_trades.parquet').exists():
            raise FileNotFoundError(name)
    for i, name in enumerate(args.windows, 1):
        print(f'[{i}/{len(args.windows)}] {name}: scoring and analysing', flush=True)
        with duckdb.connect() as con:
            con.execute(f'SET threads = {args.threads}')
            con.execute("SET memory_limit = '8GB'")
            con.execute("SET TimeZone = 'UTC'")
            con.execute(f"CREATE TEMP TABLE categories AS {CATEGORY_SQL.format(markets=RAW / 'market_data.parquet')}")
            assert con.sql('SELECT count(*) = count(DISTINCT market) FROM categories').fetchone()[0]
            result = analyse_window(con, name, WEEKLY_WINDOWS[name], expected[name])
        save_json(OUT / 'windows' / f'{name}.json', result)
        print(f"  passed: {result['target_trades']:,} trades; "
              f"flagged {result['flagged_share_fraction']:.2%} of share volume", flush=True)
    print('Completed requested windows. Build charts with 03_Analytics/weekly/make_figures.py', flush=True)


if __name__ == '__main__':
    main()

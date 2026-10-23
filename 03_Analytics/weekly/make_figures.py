"""Aggregate saved weekly outputs and render charts; does not rerun scoring.

uv run python 03_Analytics/weekly/make_figures.py
"""

import json
import math
import sys
from pathlib import Path

import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / '04_Evaluation/premise_test'))
from config import RESULTS, WEEKLY_WINDOWS  # noqa: E402

SOURCE = RESULTS / 'weekly'
HERE = Path(__file__).resolve().parent
FIG = HERE / 'figures'
PERIODS = ['Nov-Dec 2024', 'May-Jun 2025']
COLORS = {'flagged': '#D55E00', 'unflagged': '#0072B2'}
THETAS = ['0.70', '0.80', '0.90', '0.95', '0.99']
THETA_COLORS = {'0.70': '#56B4E9', '0.80': '#009E73', '0.90': '#D55E00',
                '0.95': '#CC79A7', '0.99': '#4D4D4D'}
CATS = ['Sports', 'Politics', 'Crypto', 'Economy', 'Other']


def dump(path, data):
    path.write_text(json.dumps(data, indent=2, allow_nan=False) + '\n')


def save(fig, name):
    fig.tight_layout()
    fig.savefig(FIG / f'{name}.png', dpi=160, bbox_inches='tight')
    plt.close(fig)


def main():
    FIG.mkdir(parents=True, exist_ok=True)
    rows = [json.loads((SOURCE / 'windows' / f'{name}.json').read_text()) for name in WEEKLY_WINDOWS]
    assert len(rows) == 18 and all(r['validation'] == 'passed' for r in rows)
    for r in rows:
        assert r['converged'] and r['iterations'] > 0
        assert r['lead_days'] == 30
    flat = pd.DataFrame([{**{k: v for k, v in r.items() if not isinstance(v, (list, dict))},
                          **{f'fraction_theta_{k}': v for k, v in r['theta_fractions'].items()}}
                         for r in rows])
    flat.to_csv(HERE / 'weekly_summary.csv', index=False)
    categories = pd.DataFrame([{'window': r['window'], 'period': r['period'], **c}
                               for r in rows for c in r['categories']])
    profiles = pd.DataFrame([{'window': r['window'], 'period': r['period'], **p}
                             for r in rows for p in r['profile']])
    categories.to_csv(HERE / 'weekly_categories.csv', index=False)
    profiles.to_csv(HERE / 'weekly_profiles.csv', index=False)
    days = pd.concat([pd.read_csv(SOURCE / 'daily' / f"{r['window']}.csv").assign(
        window=r['window'], period=r['period']) for r in rows], ignore_index=True)
    assert days.date.is_unique and len(days) == 122
    days.to_csv(HERE / 'daily_summary.csv', index=False)
    months = days.assign(month=days.date.str[:7]).groupby('month', as_index=False).agg(
        days=('date', 'count'), trades=('trades', 'sum'), share_volume=('share_volume', 'sum'),
        flagged_share_volume=('flagged_share_volume', 'sum'), usdc_volume=('usdc_volume', 'sum'))
    months['flagged_share_fraction'] = months.flagged_share_volume / months.share_volume
    months['share_volume_per_day'] = months.share_volume / months.days
    months.to_csv(HERE / 'monthly_summary.csv', index=False)
    total_trades = int(flat.target_trades.sum())
    assert total_trades == 29_380_522

    market_rows = []
    for r in rows:
        m = pd.read_parquet(SOURCE / 'market_theta' / f"{r['window']}.parquet")
        assert m.market.is_unique
        curves = m[[f'wf_{t}' for t in THETAS]].to_numpy()
        assert np.isfinite(curves).all() and ((curves >= 0) & (curves <= 1)).all()
        assert (np.diff(curves, axis=1) <= 1e-10).all()
        m['window'], m['period'] = r['window'], r['period']
        m['flagged_share_volume_approx'] = m.target_vol * m['wf_0.90']
        market_rows.append(m)
    markets = pd.concat(market_rows, ignore_index=True)
    markets.to_csv(HERE / 'weekly_markets.csv', index=False)
    top = markets.groupby(['period', 'market'], as_index=False).agg(
        name=('name', 'first'), share_volume=('target_vol', 'sum'),
        flagged_share_volume_approx=('flagged_share_volume_approx', 'sum'),
        active_weeks=('window', 'nunique'))
    top = pd.concat([top[top.period == period].nlargest(10, 'flagged_share_volume_approx')
                     for period in PERIODS], ignore_index=True)
    top.to_csv(HERE / 'top_flagged_markets.csv', index=False)

    # Compare labels only for wallets active in both adjacent target weeks.
    # These are rolling-window detector labels, not changes in verified behaviour.
    transitions = []
    previous = {}
    for r in rows:
        f = pd.read_parquet(SOURCE / 'wallet_flags' / f"{r['window']}.parquet",
                            columns=['wallet', 'x', 'flagged', 'target_vol'])
        f = f[f.target_vol > 0].set_index('wallet')
        period = r['period']
        if period in previous:
            prev_name, before = previous[period]
            common = before[['x', 'flagged']].join(f[['x', 'flagged']], how='inner', lsuffix='_before', rsuffix='_after')
            n = len(common)
            transitions.append({
                'period': period, 'from_window': prev_name, 'to_window': r['window'],
                'wallets_active_in_both': n,
                'flagged_to_unflagged': int((common.flagged_before & ~common.flagged_after).sum()),
                'unflagged_to_flagged': int((~common.flagged_before & common.flagged_after).sum()),
                'fraction_changing_flag': float((common.flagged_before != common.flagged_after).mean()),
                'median_absolute_score_change': float((common.x_before - common.x_after).abs().median()),
            })
        previous[period] = (r['window'], f)
    pd.DataFrame(transitions).to_csv(HERE / 'adjacent_wallet_transitions.csv', index=False)

    period_stats = {}
    for period in PERIODS:
        rr = [r for r in rows if r['period'] == period]
        d = flat[flat.period == period]
        c = categories[categories.period == period].groupby('category').sum(numeric_only=True)
        p = profiles[profiles.period == period]
        sv, fv, uv, fu = (float(d[col].sum()) for col in [
            'share_volume', 'flagged_share_volume', 'usdc_volume', 'flagged_usdc_volume'])
        assert math.isclose(c.share_volume.sum(), sv, rel_tol=1e-9)
        assert math.isclose(c.flagged_share_volume.sum(), fv, rel_tol=1e-9)
        assert list(d.target_start) == sorted(d.target_start)
        assert list(d.target_end_exclusive)[:-1] == list(d.target_start)[1:]
        profiles_by_flag = {}
        for flagged, g in p.groupby('flagged'):
            profiles_by_flag['flagged' if flagged else 'unflagged'] = {
                'top1_share': float(np.average(g.top1_share, weights=g.endpoint_volume)),
                'top2_share': float(np.average(g.top2_share, weights=g.endpoint_volume)),
                'wallet_week_observations': int(g.wallets.sum()),
            }
        period_stats[period] = {
            'weeks': len(rr), 'days': int(d.target_days.sum()), 'trades': int(d.target_trades.sum()),
            'share_volume': sv, 'flagged_share_volume': fv, 'flagged_share_fraction': fv / sv,
            'usdc_volume': uv, 'flagged_usdc_volume': fu, 'flagged_usdc_fraction': fu / uv,
            'theta_fractions': {t: sum(r['share_volume'] * r['theta_fractions'][t] for r in rr) / sv for t in THETAS},
            'weekly_fraction_min': float(d.flagged_share_fraction.min()),
            'weekly_fraction_max': float(d.flagged_share_fraction.max()),
            'lowest_week': str(d.loc[d.flagged_share_fraction.idxmin(), 'window']),
            'highest_week': str(d.loc[d.flagged_share_fraction.idxmax(), 'window']),
            'profiles': profiles_by_flag,
            'flagged_sports_fraction': float(c.loc['Sports', 'flagged_share_volume'] / fv),
            'flagged_lowprice_fraction': float(c.flagged_lowprice_share_volume.sum() / fv),
            'flagged_endpoint_fraction_mostly_with_flagged': float(
                d.flagged_endpoint_volume_mostly_with_flagged.sum() / d.flagged_endpoint_volume.sum()),
            'categories': c.reset_index().to_dict(orient='records'),
        }
    dump(HERE / 'period_summary.json', period_stats)
    dump(SOURCE / 'validation.json', {
        'windows': 18, 'passed_windows': 18, 'target_trades': total_trades,
        'target_days': len(days), 'lead_days': 30,
        'all_scores_converged': True,
        'checks': ['finite bounded wallet scores', 'weighted score conservation',
                   'extraction counts, volume and target dates', 'unique wallet IDs and score/flag agreement',
                   'wallet endpoint volume / 2 equals trade volume',
                   'monotone market theta curves agree with direct trade aggregation',
                   '122 non-overlapping target dates; period/category/daily totals agree'],
    })

    plt.rcParams.update({'axes.spines.top': False, 'axes.spines.right': False, 'font.size': 10})
    fig, axes = plt.subplots(1, 2, figsize=(12, 4), sharey=True)
    for ax, period in zip(axes, PERIODS):
        d = flat[flat.period == period]
        x = pd.to_datetime(d.target_start)
        for t in THETAS:
            main_curve = t == '0.90'
            ax.plot(x, 100 * d[f'fraction_theta_{t}'], marker='o', ms=4 if main_curve else 2,
                    lw=2.3 if main_curve else 1, alpha=1 if main_curve else 0.6,
                    label=f'θ={t}', color=THETA_COLORS[t])
        ax.set(title=period, ylim=(0, 100), ylabel='Flagged share of share volume (%)')
        ax.tick_params(axis='x', rotation=40)
        ax.grid(alpha=0.2)
    axes[1].legend(fontsize=8, frameon=False)
    save(fig, '01_weekly_theta')

    fig, axes = plt.subplots(1, 2, figsize=(12, 4), sharey=True)
    for ax, period in zip(axes, PERIODS):
        d = flat[flat.period == period]
        labels = [s[5:] + ('*' if n != 7 else '') for s, n in zip(d.target_start, d.target_days)]
        fv = d.flagged_share_volume / d.target_days / 1e6
        rest = (d.share_volume - d.flagged_share_volume) / d.target_days / 1e6
        ax.bar(labels, fv, label='flagged', color=COLORS['flagged'])
        ax.bar(labels, rest, bottom=fv, label='unflagged', color=COLORS['unflagged'])
        ax.set(title=period, ylabel='Million shares per day', xlabel='Target start (* = 5-day final window)')
        ax.tick_params(axis='x', rotation=45)
        ax.grid(axis='y', alpha=0.2)
    axes[1].legend(frameon=False)
    save(fig, '02_daily_normalized_volume')

    fig, axes = plt.subplots(1, 2, figsize=(12, 4), sharey=True)
    for ax, period in zip(axes, PERIODS):
        for flagged in [False, True]:
            g = profiles[(profiles.period == period) & (profiles.flagged == flagged)]
            starts = [WEEKLY_WINDOWS[w]['target_start'] for w in g.window]
            label = 'flagged' if flagged else 'unflagged'
            ax.plot(pd.to_datetime(starts), 100 * g.top2_share, marker='o', color=COLORS[label], label=label)
        ax.set(title=period, ylim=(0, 100), ylabel='Volume-weighted top-2 partner share (%)')
        ax.tick_params(axis='x', rotation=40)
        ax.grid(alpha=0.2)
    axes[1].legend(frameon=False)
    save(fig, '03_partner_concentration')

    fig, axes = plt.subplots(1, 2, figsize=(12, 4), sharey=True)
    for ax, period in zip(axes, PERIODS):
        c = categories[categories.period == period].groupby('category').sum(numeric_only=True).reindex(CATS).fillna(0)
        x = np.arange(len(CATS))
        for offset, label in [(-0.2, 'unflagged'), (0.2, 'flagged')]:
            v = c.flagged_share_volume if label == 'flagged' else c.share_volume - c.flagged_share_volume
            ax.bar(x + offset, 100 * v / v.sum(), width=0.38, label=label, color=COLORS[label])
        ax.set_xticks(x, CATS, rotation=25)
        ax.set(title=period, ylabel="Share of each group's volume (%)", ylim=(0, 100))
    axes[1].legend(frameon=False)
    save(fig, '04_category_mix')
    print(json.dumps(period_stats, indent=2))
    print('Saved CSV tables, period_summary.json, validation.json, and four figures.')


if __name__ == '__main__':
    main()

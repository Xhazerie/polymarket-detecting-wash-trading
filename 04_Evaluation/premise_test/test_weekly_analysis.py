"""Known-answer integration checks, including a shortened final target window.

Run: uv run python -m unittest discover -s 04_Evaluation/premise_test -p 'test_weekly_analysis.py'
"""

import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import duckdb
import pandas as pd

spec = importlib.util.spec_from_file_location('weekly', Path(__file__).with_name('09_weekly_analysis.py'))
weekly = importlib.util.module_from_spec(spec)
spec.loader.exec_module(weekly)


class WeeklyAnalysisTest(unittest.TestCase):
    def test_known_wash_pair_and_unclosed_pair_with_two_day_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            out = root / 'results/weekly'
            for sub in ['wallet_flags', 'market_theta', 'daily']:
                (out / sub).mkdir(parents=True)
            name = 'test'
            trades = pd.DataFrame({
                'block': [1, 2, 3], 'log_index': [0, 0, 0],
                'ts': pd.to_datetime(['2024-12-01', '2024-12-02', '2024-12-01'], utc=True),
                'market': ['wash', 'wash', 'hold'], 'maker': ['a', 'a', 'c'],
                'taker': ['b', 'b', 'd'], 'shares': [10., 10., 5.],
                'dp_maker': [10., -10., 5.], 'usdc': [.1, .1, 2.5], 'in_target': True,
            })
            trades.to_parquet(root / 'test_trades.parquet')
            metadata = pd.DataFrame({
                'condition': ['wash', 'wash', 'hold'],
                'marketName': ['NBA finals?', 'NBA finals?', 'Bitcoin price?'],
                'marketSlug': ['nba-finals', 'nba-finals', 'bitcoin'],
                'startDate': ['2024-11-15'] * 3,
            })
            md = root / 'metadata.parquet'
            metadata.to_parquet(md)
            w = {'lead_start': '2024-11-01', 'target_start': '2024-12-01', 'target_end': '2024-12-03'}
            expected = {'target_trades': 3, 'target_markets': 2, 'target_share_volume': 25.}
            with patch.object(weekly, 'INTERIM', root), patch.object(weekly, 'OUT', out), \
                 patch.object(weekly.flags, 'INTERIM', root), patch.object(weekly.flags, 'RESULTS', root / 'results'), \
                 patch.object(weekly.theta.alg1, 'INTERIM', root), patch.object(weekly.theta, 'MARKETS', str(md)), \
                 duckdb.connect() as con:
                con.execute("SET TimeZone = 'UTC'")
                con.execute(f"CREATE TEMP TABLE categories AS {weekly.CATEGORY_SQL.format(markets=md)}")
                self.assertEqual(con.sql('SELECT count(*) FROM categories').fetchone()[0], 2)
                got = weekly.analyse_window(con, name, w, expected)
                self.assertEqual(got['target_days'], 2)
                self.assertEqual(got['active_wallets'], 4)
                self.assertEqual(got['active_flagged_wallets'], 2)
                self.assertEqual(got['flagged_share_fraction'], .8)
                self.assertEqual(got['flagged_share_volume'], 20.)
                self.assertEqual(got['share_volume_per_day'], 12.5)
                self.assertEqual(list(got['theta_fractions'].values()), [.8] * 5)
                self.assertTrue(got['converged'])
                f = pd.read_parquet(out / 'wallet_flags/test.parquet').set_index('wallet')
                self.assertEqual(set(f.index[f.flagged]), {'a', 'b'})
                # Reused scores must produce exactly the same market curves as a fresh score run.
                direct = weekly.theta.market_theta(con, name, w)
                reused = pd.read_parquet(out / 'market_theta/test.parquet')
                pd.testing.assert_frame_equal(direct.sort_values('market').reset_index(drop=True),
                                              reused.sort_values('market').reset_index(drop=True))
                direct_dir = out / 'fresh'
                direct_dir.mkdir()
                weekly.flags.wallet_flags(con, name, direct_dir)
                fresh_flags = pd.read_parquet(direct_dir / 'test.parquet').sort_values('wallet').reset_index(drop=True)
                reused_flags = f.reset_index().sort_values('wallet').reset_index(drop=True)
                pd.testing.assert_frame_equal(fresh_flags, reused_flags)


if __name__ == '__main__':
    unittest.main()

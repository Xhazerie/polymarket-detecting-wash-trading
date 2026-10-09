# Raw data

**Source:** [moose-code/polymarket-onchain-v1](https://huggingface.co/datasets/moose-code/polymarket-onchain-v1)
(Envio HyperIndex, CC-BY-4.0). Polygon on-chain events for Polymarket, Sep 2020 – Apr 2026.

| File | Used for | Size |
|---|---|---|
| `order_filled/year=YYYY/month=MM.parquet` | every CLOB fill (the trades) | ~0.52–1.43 GB/month for the six required months |
| `condition.parquet` | token id → (market, outcome index) via `positionIds` | 126 MB |
| `market_data.parquet` | market question/slug/outcomes (EDA, categories) | 137 MB |

The 18 weekly windows use **30 days** of history. Download October–December 2024
and April–June 2025: six monthly files, about 4.99 GB, plus 263 MB of metadata.
The earliest window starts November 1, 2024, with history starting October 2, 2024.
Other downloaded months remain available for the separate 90/180-day sensitivity experiments.

Fresh download from the repository root (into `data/raw/`, gitignored):

```bash
B=https://huggingface.co/datasets/moose-code/polymarket-onchain-v1/resolve/main
mkdir -p data/raw/order_filled
for ym in 2024/10 2024/11 2024/12 2025/04 2025/05 2025/06; do
  y=${ym%/*}; m=${ym#*/}
  curl -fL --retry 3 -o "data/raw/order_filled/$y-$m.parquet" \
    "$B/order_filled/year=$y/month=$m.parquet" || exit "$?"
done
curl -fL --retry 3 -o data/raw/condition.parquet   "$B/condition.parquet"
curl -fL --retry 3 -o data/raw/market_data.parquet "$B/market_data.parquet"
```

These commands overwrite existing files. If the required files are already
complete, proceed to extraction. To resume a specific interrupted file, repeat
its `curl` command with `-C -`.

Field conventions (from the dataset card): addresses are hex (mixed case in `order_filled`
→ we lowercase), amounts are strings in 6-decimal units (÷ 1e6), `assetId = '0'` is USDC,
`id` = `chain_block_logIndex`, `timestamp` = unix seconds as a string.

Do **not** pull 2026 months (9–21 GB each, outside the period the paper measured).

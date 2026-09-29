# Raw data

**Source:** [moose-code/polymarket-onchain-v1](https://huggingface.co/datasets/moose-code/polymarket-onchain-v1)
(Envio HyperIndex, CC-BY-4.0). Polygon on-chain events for Polymarket, Sep 2020 – Apr 2026.

| File | Used for | Size |
|---|---|---|
| `order_filled/year=YYYY/month=MM.parquet` | every CLOB fill (the trades) | 0.6–1.4 GB/month for our windows |
| `condition.parquet` | token id → (market, outcome index) via `positionIds` | 126 MB |
| `market_data.parquet` | market question/slug/outcomes (EDA, categories) | 137 MB |

Download (into `Project/data/raw/`, gitignored):

```bash
B=https://huggingface.co/datasets/moose-code/polymarket-onchain-v1/resolve/main
for ym in 2024/11 2024/12 2025/05 2025/06; do
  y=${ym%/*}; m=${ym#*/}
  curl -L -o data/raw/order_filled/$y-$m.parquet "$B/order_filled/year=$y/month=$m.parquet"
done
curl -L -o data/raw/condition.parquet   "$B/condition.parquet"
curl -L -o data/raw/market_data.parquet "$B/market_data.parquet"
```

Field conventions (from the dataset card): addresses are hex (mixed case in `order_filled`
→ we lowercase), amounts are strings in 6-decimal units (÷ 1e6), `assetId = '0'` is USDC,
`id` = `chain_block_logIndex`, `timestamp` = unix seconds as a string.

Do **not** pull 2026 months (9–21 GB each, outside the period the paper measured).

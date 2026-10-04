# polymarket-detecting-wash-trading

ตรวจจับการซื้อขายสมรู้ร่วมคิด (**wash trading**) บน Polymarket — Assignment #2 "Analytics on Complex Data" (01204465)

เราวิเคราะห์ข้อมูล on-chain ของ Polymarket แบบ**เครือข่าย** (กระเป๋า = node, การเทรด = edge) เพื่อหากระเป๋าที่ซื้อขายวนกันเองเพื่อปั่น volume
ใช้ network-based scoring (Algorithm 1 ของ Sirolly et al., 2025) ร่วมกับ EDA, community detection และ anomaly detection
และเปรียบเทียบช่วงที่ wash สูง (ธ.ค. 2024) กับช่วงที่ wash ต่ำ (มิ.ย. 2025)

## สถานะ

| งาน | ผล |
|---|---|
| Premise test (Algorithm 1, θ = 0.9) | ✅ ธ.ค. 2024 ถูกติดธง **61.8%** · มิ.ย. 2025 **0.35%** |
| EDA รอบ 1 (สองสัปดาห์เป้าหมาย) | ✅ ดู [`03_Analytics/eda/`](03_Analytics/eda/) |
| Pipeline ช่วงเต็ม · evaluation (θ-sensitivity, synthetic injection, precision@k) · EDA รอบ 2 | ⬜ กำลังทำ |

ไทม์ไลน์ บทบาท และการตัดสินใจทั้งหมดอยู่ใน [`PROGRESS.md`](PROGRESS.md)

## โครงสร้าง

| โฟลเดอร์ | เนื้อหา |
|---|---|
| `01_Raw_Data/` | แหล่งข้อมูลและวิธีดาวน์โหลด (ตัวข้อมูลไม่ได้อยู่ใน repo) |
| `03_Analytics/eda/` | `eda_round1.ipynb` (มีคำอธิบายทุก cell) · `eda_facts.md` (ข้อเท็จจริงจากข้อมูล) · `findings.md` (ข้อค้นพบสำหรับทีม) · `figures/` · `eda_stats.json` |
| `04_Evaluation/premise_test/` | `config.py` (หน้าต่างเวลา, พารามิเตอร์) · `01_extract.py` (fills → เทรด) · `02_alg1.py` (Algorithm 1) · `results/` |
| `05_AI_Usage_Log/` | บันทึกการใช้ AI |

> เอกสารเก่าบางไฟล์อ้าง path เป็น `Project/...` — โฟลเดอร์ `Project/` นั้นคือ root ของ repo นี้

## วิธีรัน

ต้องมี [uv](https://docs.astral.sh/uv/) และ Python ≥ 3.12 · ทุกคำสั่งรันจาก root ของ repo

```bash
uv sync                                   # ติดตั้ง dependency จาก uv.lock

# 1) ดาวน์โหลดข้อมูลดิบ (~3.7 GB) ลง data/raw/ ตามคำสั่งใน 01_Raw_Data/README.md

# 2) premise test (~15 วินาทีบนเครื่อง 32 เธรด)
cd 04_Evaluation/premise_test
uv run python 01_extract.py              # -> data/interim/<window>_trades.parquet
uv run python 02_alg1.py                 # -> results/alg1_results.json
cd ../..

# 3) EDA (< 1 นาที)
uv run jupyter nbconvert --to notebook --execute --inplace 03_Analytics/eda/eda_round1.ipynb
```

`data/` และไฟล์ `*.parquet` ถูก gitignore ไว้ เพราะดาวน์โหลดใหม่ได้และมีขนาดใหญ่

## ข้อมูลและอ้างอิง

- ข้อมูล: [moose-code/polymarket-onchain-v1](https://huggingface.co/datasets/moose-code/polymarket-onchain-v1) (Hugging Face, CC-BY-4.0)
- Algorithm 1 (network-based wash-trading score): Sirolly et al. (2025), §5.1

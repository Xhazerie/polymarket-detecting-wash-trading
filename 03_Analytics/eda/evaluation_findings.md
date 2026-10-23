# ผล evaluation และ EDA รอบสอง — 23 ตุลาคม 2026

รันบนข้อมูลจริงของสอง baseline weeks: 1–7 ธ.ค. 2024 และ 1–7 มิ.ย. 2025 พร้อมประวัติย้อนหลังตาม `config.WINDOWS` ผลนี้ยังไม่ครอบคลุม 18 weekly windows และคำว่า “ติดธง” หมายถึงผล Algorithm 1 ไม่ใช่หลักฐานยืนยัน wash trading

## 1. Synthetic injection

ผล: `04_Evaluation/premise_test/results/synthetic_injection.json`

ฉีด 48 rings รวม 144 กระเป๋าที่ทราบพฤติกรรมเข้าในข้อมูล มิ.ย. แต่ละระดับ intensity มี 24 กระเป๋า ที่ θ = 0.9 จับได้ 48/144 ใบ (recall 33.33%)

| Wash intensity | Median final score | Recall ที่ θ=0.9 |
|---|---:|---:|
| 1.00 | 1.0000 | 100% |
| 0.95 | 0.9268 | 100% |
| 0.90 | 0.8571 | 0% |
| 0.85 | 0.7907 | 0% |
| 0.80 | 0.7273 | 0% |
| 0.70 | 0.6087 | 0% |

Precision@144 = 0, precision@288 = 0, precision@720 = 3.33%; Average Precision = 0.0046 ภายใต้กติกา tie-break ที่ให้กระเป๋าจริงอยู่ก่อนกระเป๋าที่ฉีดเมื่อ score เท่ากัน ค่าต่ำนี้ต้องรายงาน ไม่ควรสรุปว่า detector จัดอันดับได้ดี

กระเป๋าจริงเป็นข้อมูลที่ไม่ทราบ label แต่ถูกนับเป็น negative ใน metric นี้ จึงไม่ใช่ค่าประมาณ precision ของ wash trading จริง การมี flagged volume ต่ำใน มิ.ย. ไม่ได้แปลว่าไม่มีกระเป๋าจริง score สูง โดยมี 96,237 กระเป๋าจริงที่ score ≥ กระเป๋าฉีดที่ได้ score ต่ำที่สุด (นับรวม lead-in)

Injection เป็น component แยกจากกระเป๋าจริง และสร้างพฤติกรรม closure ตามที่ detector ออกแบบให้จับ จึงตรวจได้ว่าจับ pattern นี้หรือไม่ แต่ยังไม่ทดสอบ wash ที่ปะปนกับคู่เทรดจริง ทั้งยังมีเพียงแบบจำลอง deterministic นี้ ไม่มี confidence interval กระเป๋าที่มี intensity 0.90 ไม่จำเป็นต้องได้ final score 0.90 เพราะ score แพร่ผ่านคู่เทรดด้วย

## 2. ธงรายกระเป๋าและ EDA รอบสอง

ผล: `results/wallet_flags/{dec2024,jun2025}.parquet`, `summary.json` และ `03_Analytics/eda/eda_round2_stats.json`

| ตัวชี้วัด | ธ.ค. 2024 | มิ.ย. 2025 |
|---|---:|---:|
| กระเป๋าทั้งหมด รวม lead-in | 334,362 | 295,526 |
| กระเป๋าติดธง รวม lead-in | 77,906 (23.30%) | 25,086 (8.49%) |
| กระเป๋าที่เทรดใน target week | 104,186 | 87,130 |
| กระเป๋าติดธงที่เทรดใน target week | 30,535 (29.31%) | 6,403 (7.35%) |
| Target share volume ที่ทั้งสองฝั่งติดธง | 61.82% | 0.35% |
| Top-1 partner share: flagged / unflagged | 47.35% / 18.30% | 33.71% / 18.72% |
| Top-2 partner share: flagged / unflagged | 64.81% / 28.03% | 59.44% / 28.89% |
| Sports เป็นสัดส่วนของ flagged volume | 68.17% | 19.29% |
| ราคา < 0.02 เป็นสัดส่วนของ flagged volume | 77.33% | 62.61% |

Partner shares เป็นค่าเฉลี่ยถ่วงด้วย target volume ของกระเป๋า กระเป๋าติดธงมีการกระจุกกับคู่เทรดมากกว่า แต่ยังพิสูจน์วงแหวนไม่ได้ หมวดตลาดเป็น keyword heuristic และกฎบางส่วนต่างจากรอบแรก จึงต้องจัดหมวดใหม่ให้ตรงกันก่อนเทียบสัดส่วนหมวดระหว่าง notebook

กราฟ score ของ ธ.ค. มี volume สูงใกล้ score 1 ส่วน มิ.ย. กระจายกว้างช่วงประมาณ 0.2–0.9 จึงไม่ควรบังคับอธิบายว่าทั้งสองช่วงเป็น bimodal

ใน ธ.ค. 90.98% ของ volume ฝั่งกระเป๋าที่ติดธงมาจากกระเป๋าที่มี volume ≥90% กับคู่เทรดที่ติดธงด้วยกัน เทียบกับ 21.11% ใน มิ.ย. แต่ median ต่อกระเป๋าเท่ากับ 51.91% และ 41.18% สะท้อนว่ากระเป๋าขนาดใหญ่ขับผลถ่วง volume ไม่ได้แปลว่ากระเป๋าส่วนใหญ่เทรดเป็นกลุ่มปิด อีกทั้ง score ใช้คู่เทรดเป็นส่วนหนึ่งของนิยาม จึงไม่ใช่ validation อิสระ และยังสรุป chip dumping ไม่ได้

## 3. θ-sensitivity และเคส Trump

ผล: `results/market_theta/` มี parquet รายตลาด, `case_study.json` และ `trump_case_study.png`

ตลาด “Will Donald Trump be inaugurated?” มี volume ที่ถูกติดธง **89.12% ที่ θ=0.90 → 20.88% ที่ θ=0.99** เหลือ 23.43% ของ flag เดิม และตลาดเปิดภายใน lead-in จึงแสดงความไวต่อ threshold อย่างชัดเจน แต่ **ยังยืนยัน false positive ไม่ได้** ต้องมีหลักฐานพฤติกรรมเพิ่มเติม

เกณฑ์เชิงพรรณนา `robust_wash` คือ flagged fraction ที่ θ=0.90 ≥50% และอัตราส่วน flagged fraction ที่ θ=0.99 ต่อ θ=0.90 ≥50% พบ 132 ตลาดใน ธ.ค. และ 11 ตลาดใน มิ.ย. ชื่อ field นี้ไม่ใช่ ground truth ความทนต่อ threshold เพียงอย่างเดียวไม่ยืนยัน wash

## 4. การตรวจผลและรันซ้ำ

`results/real_data_validation.json` บันทึกว่าธงตรงกับ score, wallet IDs ไม่ซ้ำ, scores/volumes มีค่าถูกต้อง, ผลรวม volume รายกระเป๋าหารสองตรงกับ volume รายเทรด, ผลตรงกับ baseline เดิม และ flagged fractions รายตลาดไม่เพิ่มเมื่อ θ สูงขึ้น ทั้ง 2,307 และ 3,918 ตลาดผ่านการตรวจนี้ Notebook รันครบ 11 code cells โดยไม่มี error output พร้อมกราฟ 4 รูปใน `figures/r2_*.png`

รันจาก root ของ repo หลังติดตั้ง dependencies:

```bash
uv run python 04_Evaluation/premise_test/06_synthetic_injection.py
uv run python 04_Evaluation/premise_test/07_wallet_flags.py
uv run python 04_Evaluation/premise_test/08_market_theta.py
uv run python -m nbconvert --to notebook --execute --inplace --ExecutePreprocessor.timeout=600 03_Analytics/eda/eda_round2.ipynb
```

Parquet รายกระเป๋า/รายตลาดเก็บในเครื่องตาม `.gitignore` ของ repo ส่วน summaries, evaluation JSON, notebook พร้อม outputs และกราฟเก็บเป็นผลสำหรับ review ได้ ข้อจำกัดเรื่อง position ก่อน lead-in และการไม่มี historical balance ground truth ยังคงใช้กับการตีความทั้งหมดนี้

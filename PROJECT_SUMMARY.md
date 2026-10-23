# สรุปโปรเจกต์: ตรวจจับ wash trading บน Polymarket

อัปเดต: 23 ตุลาคม 2026 · Assignment #2: Analytics on Complex Data

**ผลหลัก:** เมื่อวิเคราะห์ครบ พ.ย.–ธ.ค. 2024 และ พ.ค.–มิ.ย. 2025 ด้วย Algorithm 1 ที่ θ=0.90 พบ share volume ที่ถูกติดธง **49.00% เทียบกับ 2.50%** ความต่างยังอยู่ทุก threshold ที่ทดลอง แต่ผลนี้เป็นการตรวจจับรูปแบบที่น่าสงสัย ไม่ใช่การยืนยันว่าการซื้อขายทั้งหมดที่ติดธงเป็น wash trading จริง

เอกสารนี้รวมสถานะ วิธีทำ ผล baseline, EDA, evaluation และการวิเคราะห์ครบ 18 สัปดาห์ พร้อมลิงก์ไปยังหลักฐานและไฟล์สำหรับทำรายงาน/สไลด์

## 1. คำถามและวิธีวิเคราะห์

คำถามหลักคือเครือข่ายกระเป๋าที่ซื้อขายบน Polymarket มีรูปแบบการปิด position และการกระจุกกับคู่เทรดที่แตกต่างกันระหว่างสองช่วงเวลาหรือไม่ และรูปแบบดังกล่าวไวต่อพารามิเตอร์เพียงใด

ใช้กระเป๋าเป็น node และการซื้อขายเป็น edge โดยนำ Algorithm 1 จาก Sirolly et al. (2025) มาเป็นวิธีให้คะแนน แล้ววิเคราะห์ข้อมูลและประเมินผลของโปรเจกต์เอง:

1. สร้างประวัติ position ต่อคู่ wallet–market จาก matched trades
2. ตรวจว่ามีการกลับทิศ position หรือการลด position จนใกล้ศูนย์ตาม closure rule หรือไม่ (`C_CLOSURE=0.005`)
3. สร้างคะแนนเริ่มต้น `x0` จากสัดส่วน volume ของกระเป๋าในตลาดที่พบ closure
4. ปรับคะแนนด้วยคู่เทรดจนลู่เข้า: `x ← (x0 + Bx) / 2` โดย `B` เป็นสัดส่วน volume ที่เทรดกับแต่ละคู่ และใช้ relative tolerance `1e-5`
5. กระเป๋าถูกติดธงเมื่อ `x ≥ θ`; **trade ถูกติดธงเมื่อทั้งสองกระเป๋าผ่านเกณฑ์** ใช้ θ=0.90 เป็นค่าหลักและตรวจ 0.70/0.80/0.90/0.95/0.99

Score อยู่ในช่วง 0–1 แต่ยังไม่ได้ปรับเทียบให้เป็นความน่าจะเป็นของ wash trading ส่วนการเทรดที่ไม่ติดธงก็ยังไม่ได้รับการยืนยันว่าไม่มี wash

## 2. ข้อมูลและ preprocessing

แหล่งข้อมูล: `moose-code/polymarket-onchain-v1` บน Hugging Face ใช้ `order_filled`, `condition` และ `market_data` ดูรายละเอียดใน [01_Raw_Data/README.md](01_Raw_Data/README.md)

หนึ่งแถวหลัง preprocessing คือ matched trade หนึ่งครั้ง ใช้เฉพาะ maker-fill rows และตัด taker-summary rows ของ exchange ซึ่งซ้ำกับ maker fills ออก จากนั้นแปลงจำนวนจากหน่วยหกทศนิยม ทำ address เป็น lowercase และ map token เป็นตลาด/ผลลัพธ์ เวลาอ้างอิงเป็น UTC

ตัวชี้วัดหลักคือ **share volume** ไม่ใช่จำนวนเงิน ตัวเลข USDC รายงานแยกกัน และ flagged USDC volume ไม่ใช่กำไรหรือเงินเสียหาย

| ชุดวิเคราะห์ | Target period | ประวัติย้อนหลัง |
|---|---|---|
| Baseline ธ.ค. | 1–7 ธ.ค. 2024 | เริ่ม 1 พ.ย. 2024 |
| Baseline มิ.ย. | 1–7 มิ.ย. 2025 | เริ่ม 1 พ.ค. 2025 |
| Weekly ช่วงปี 2024 | 1 พ.ย.–31 ธ.ค. 2024 รวม 9 windows | 30 วันก่อนแต่ละ window |
| Weekly ช่วงปี 2025 | 1 พ.ค.–30 มิ.ย. 2025 รวม 9 windows | 30 วันก่อนแต่ละ window |

Weekly windows เริ่มจาก 1 พ.ย./1 พ.ค. แล้วเลื่อนไปทีละ 7 วัน โดย window สุดท้ายของแต่ละช่วงมี 5 วัน รวม **18 windows, 122 target days และ 29,380,522 target trades** Baseline เป็นส่วนที่ทับกับช่วงเต็ม จึงห้ามบวกจำนวน trades/volume baseline เข้ากับ weekly totals อีก

รวม volume ข้าม windows เฉพาะ `in_target` เพื่อไม่ให้ประวัติ lead-in ที่ทับกันถูกนับซ้ำ ผลรวมรายช่วงใช้ผลรวม flagged volume หารผลรวม volume ไม่ใช่ค่าเฉลี่ย percentages รายสัปดาห์

## 3. ผล baseline และ EDA รอบแรก

| ตัวชี้วัดของ target week | ธ.ค. 2024 | มิ.ย. 2025 |
|---|---:|---:|
| Trades | 1,635,178 | 1,147,205 |
| กระเป๋าที่ active | 104,186 | 87,130 |
| Markets | 2,307 | 3,918 |
| Share volume | 692.9 M | 389.8 M |
| USDC volume | 182.7 M | 169.3 M |
| **Flagged share volume ที่ θ=0.90** | **61.82%** | **0.35%** |

EDA รอบแรกพบว่า ธ.ค. มี volume จากกระเป๋าที่กระจุกกับคู่เทรดสองรายมากกว่า มีสัดส่วน share volume ที่ราคาต่ำกว่า 0.02 USDC สูงกว่า และพบขนาด trade 96 shares ซ้ำบ่อย ข้อสังเกตเหล่านี้เป็นสัญญาณให้ตรวจต่อ ไม่ใช่ labels ของ wash ที่ทราบคำตอบ

หลักฐาน: [ข้อเท็จจริง EDA รอบแรก](03_Analytics/eda/eda_facts.md), [ข้อค้นพบรอบแรก](03_Analytics/eda/findings.md), [ผล Algorithm 1](04_Evaluation/premise_test/results/alg1_results.json)

## 4. ผลครบ 18 weekly windows

| ตัวชี้วัด | พ.ย.–ธ.ค. 2024 | พ.ค.–มิ.ย. 2025 |
|---|---:|---:|
| Target trades | 19,111,285 | 10,269,237 |
| Share volume | 6,712.06 M | 2,667.56 M |
| Flagged share volume | 3,289.07 M | 66.82 M |
| **Flagged share fraction ที่ θ=0.90** | **49.00%** | **2.50%** |
| USDC volume | 1,979.45 M | 1,132.02 M |
| Flagged USDC fraction | 39.63% | 2.14% |
| ช่วง flagged share fraction รายสัปดาห์ | 13.65–63.76% | 0.15–5.25% |

| เดือน จัดตามวันเทรดจริง | Flagged share fraction |
|---|---:|
| พ.ย. 2024 | 37.69% |
| ธ.ค. 2024 | 61.09% |
| พ.ค. 2025 | 4.37% |
| มิ.ย. 2025 | 0.64% |

สัปดาห์เริ่ม 1 พ.ย. มี share volume สูงถึง 1,513.47 M แต่ติดธงเพียง 13.65% ขณะที่อีกแปด windows ในช่วงเดียวกันอยู่ที่ 54.43–63.76% จึงไม่ควรใช้ baseline ธ.ค. สัปดาห์เดียวแทนผลทั้งสองเดือน

ในปี 2025 flagged fraction ลดลงจากช่วงต้น พ.ค. แต่ไม่ได้ลดต่อเนื่องทุกสัปดาห์ โดย window 26–30 มิ.ย. เพิ่มเป็น 1.95% และประมาณ 94.7% ของ flagged volume ใน window นี้มาจากตลาด Lewis Hamilton เพียงตลาดเดียว

![Weekly threshold sensitivity](03_Analytics/weekly/figures/01_weekly_theta.png)

หลักฐาน: [ข้อค้นพบครบช่วง](03_Analytics/weekly/findings.md), [ตารางรายสัปดาห์](03_Analytics/weekly/weekly_summary.csv), [รายเดือน](03_Analytics/weekly/monthly_summary.csv), [ผลรวมรายช่วง](03_Analytics/weekly/period_summary.json)

## 5. θ-sensitivity

| θ | Flagged share fraction พ.ย.–ธ.ค. | Flagged share fraction พ.ค.–มิ.ย. |
|---|---:|---:|
| 0.70 | 66.50% | 18.83% |
| 0.80 | 59.94% | 7.51% |
| 0.90 | 49.00% | 2.50% |
| 0.95 | 44.82% | 1.13% |
| 0.99 | 39.46% | 0.87% |

ความต่างระหว่างช่วงยังอยู่ทุก θ ที่ทดลอง แต่ระดับ flagged volume เปลี่ยนตามเกณฑ์อย่างมีสาระ จึงต้องรายงาน sensitivity ควบคู่กับค่าหลัก ไม่ตีความ 49.00% หรือ 2.50% เป็นสัดส่วน wash ที่ทราบแน่นอน

## 6. EDA ของกระเป๋าที่ติดธง

ผลต่อไปนี้ใช้ครบ 18 สัปดาห์ โดย partner shares ถ่วงด้วย target volume ฝั่งกระเป๋า:

| ตัวชี้วัด | พ.ย.–ธ.ค. | พ.ค.–มิ.ย. |
|---|---:|---:|
| Top-1 partner share: flagged / unflagged | 42.49% / 18.92% | 31.27% / 19.83% |
| Top-2 partner share: flagged / unflagged | 55.54% / 28.51% | 56.77% / 30.00% |
| ราคา <0.02 เป็นสัดส่วนของ flagged share volume | 72.59% | 37.02% |
| Sports เป็นสัดส่วนของ flagged share volume ตามคีย์เวิร์ด | 48.77% | 18.51% |

กระเป๋าที่ติดธงมี volume กระจุกกับคู่เทรดมากกว่า แต่ score ใช้ความสัมพันธ์คู่เทรดอยู่แล้ว จึงเป็นการอธิบาย detector ไม่ใช่ validation อิสระ และยังไม่ยืนยันวงแหวนหรือ chip dumping

หมวดตลาดเป็น keyword heuristic ไม่ใช่หมวดทางการ ตัวอย่างเช่นชื่อ Lewis Hamilton ไม่ถูกจับเป็น Sports ด้วยกฎปัจจุบัน หมวด Other จึงรวมทั้งภาพยนตร์และกีฬาที่กฎจับไม่ครบ อีกทั้งกฎ EDA รอบแรกมีบางส่วนต่างจากรอบสอง จึงควรจัดหมวดให้ตรงกันก่อนเทียบผลข้าม notebook

Wallet เดิมอาจเปลี่ยนธงเมื่อเลื่อนช่วงประวัติ สำหรับ wallets ที่ active ใน windows ติดกันพบสัดส่วนเปลี่ยน flag 5.74–15.85% ใน พ.ย.–ธ.ค. และ 1.95–4.93% ใน พ.ค.–มิ.ย. การบวกจำนวนกระเป๋ารายสัปดาห์จะได้ wallet-week observations ไม่ใช่จำนวน wallets ไม่ซ้ำตลอดช่วง

กราฟเพิ่มเติม: [volume ต่อวัน](03_Analytics/weekly/figures/02_daily_normalized_volume.png), [partner concentration](03_Analytics/weekly/figures/03_partner_concentration.png), [category mix](03_Analytics/weekly/figures/04_category_mix.png)

## 7. Synthetic evaluation: ทดสอบด้วย pattern ที่ทราบคำตอบ

ฉีด 48 rings รวม 144 กระเป๋าเข้าในข้อมูล baseline มิ.ย. แบบ component แยกจากกระเป๋าจริง ใช้ intensity 6 ระดับ ระดับละ 24 กระเป๋า ที่ θ=0.90:

| Intensity | Median final score | Recall |
|---|---:|---:|
| 1.00 | 1.0000 | 100% |
| 0.95 | 0.9268 | 100% |
| 0.90 | 0.8571 | 0% |
| 0.85 | 0.7907 | 0% |
| 0.80 | 0.7273 | 0% |
| 0.70 | 0.6087 | 0% |

รวมจับได้ **48/144 กระเป๋า หรือ recall 33.33%** คะแนนสุดท้ายไม่จำเป็นต้องเท่ากับ intensity เพราะมีการแพร่คะแนนผ่านคู่เทรดด้วย

**Precision@144 = 0, precision@288 = 0, precision@720 = 3.33% และ AP = 0.0046** โดยจัดกระเป๋าจริงก่อนกระเป๋าฉีดเมื่อ score เท่ากัน ต้องรายงานค่าต่ำนี้อย่างตรงไปตรงมา และไม่สรุปว่าระบบจัดอันดับได้ดี

กระเป๋าจริงไม่มี labels แต่ถูกนับเป็น negatives ใน metric นี้ จึงไม่ใช่ค่าประมาณ precision ของ wash trading จริง การทดลองยังใช้ pattern ที่สอดคล้องกับ closure rule และไม่ได้ทดสอบกรณีที่ rings ปะปนกับคู่เทรดจริง

หลักฐาน: [ผล synthetic injection](04_Evaluation/premise_test/results/synthetic_injection.json), [คำอธิบาย evaluation และ baseline EDA รอบสอง](03_Analytics/eda/evaluation_findings.md)

## 8. เคสที่ต้องตีความระมัดระวัง

**Trump inauguration:** ใน baseline ธ.ค. ถูกติดธง 89.12% ที่ θ=0.90 แต่เหลือ 20.88% ที่ θ=0.99 และตลาดเปิดภายใน lead-in จึงไม่ใช่กรณีที่ประวัติตลาดก่อนเปิดหายไป เมื่อดู weekly windows ก็ยังพบความไวต่อ threshold แต่ยังยืนยัน false positive ไม่ได้ ต้องตรวจพฤติกรรมเพิ่มเติม

**Hamilton ใน window สุดท้าย มิ.ย.:** flagged volume ประมาณ 3.85 M shares จาก 4.07 M ทั้ง window สะท้อนความกระจุกเฉพาะตลาด ไม่ใช่หลักฐานว่าทุกตลาดกลับมามี wash สูง อีกทั้งเป็นตัวอย่างข้อจำกัดของการจัดหมวดด้วยคีย์เวิร์ด

หลักฐาน: [Trump case study](04_Evaluation/premise_test/results/market_theta/case_study.json), [ตลาดที่มี flagged volume สูงสุด](03_Analytics/weekly/top_flagged_markets.csv), [market curves รายสัปดาห์](03_Analytics/weekly/weekly_markets.csv)

## 9. Validation และ lead-in sensitivity

- Preprocessing ทั้ง 18 windows ผ่าน integrity checks: ไม่พบ unmapped-token rows หรือ self-trades ตาม extraction report
- ตรวจ sampled position consistency จาก raw fills รวม 1,800 pair/window cases และ 13,613 block checkpoints ไม่พบความต่าง แต่ไม่ใช่การยืนยัน starting balances จริง
- ทดลอง baseline ด้วยประวัติย้อนหลัง 30/90/180 วัน: flagged fraction ของ ธ.ค. เป็น 61.82%/61.82%/61.64% และ มิ.ย. เป็น 0.34%/0.30%/0.38% ความต่างรายช่วงยังอยู่ แต่คะแนนและธงรายกระเป๋าเปลี่ยนได้
- June แบบ exact 30 วันเริ่ม 2 พ.ค. ต่างจาก baseline เดิมที่เริ่ม 1 พ.ค. จึงไม่ควรตีความผล 0.34% vs 0.35% ว่าเป็นความขัดแย้ง
- ผล weekly ครบ 18 windows ผ่าน convergence, finite bounded scores, weighted score conservation, date/count/volume checks, wallet flag checks และ θ-monotonicity ตรวจยอดรวมรายวัน/หมวด/period ตรงกันและไม่มี target dates ซ้ำ
- Integration test ด้วยคู่กระเป๋าที่เปิดแล้วปิดเทียบกับคู่ที่เปิดแล้วถือผ่าน รวมถึง window แบบสั้น, metadata ซ้ำ และการใช้คะแนนร่วมกันเทียบกับคำนวณใหม่ Notebook baseline EDA รอบสองรันครบ 11 code cells ไม่มี error

หลักฐาน: [preprocessing progress](02_Preprocessing/PROGRESS.md), [position validation](02_Preprocessing/POSITION_VALIDATION.md), [lead-in sensitivity](02_Preprocessing/LEAD_IN_SENSITIVITY.md), [weekly validation](04_Evaluation/premise_test/results/weekly/validation.json)

## 10. ข้อจำกัดที่ต้องอยู่ในรายงาน

1. ไม่มี real-world ground truth จึงยังไม่รู้ precision/false-positive rate จริง และ score ไม่ใช่ความน่าจะเป็นที่ปรับเทียบแล้ว
2. ไม่ทราบ position ก่อน lead-in; `user_position` เป็น snapshot เม.ย. 2026 จึงเทียบกับจุดจบ windows ปี 2024/2025 โดยตรงไม่ได้
3. θ และความยาวประวัติมีผลต่อ score/labels ต้องรายงาน sensitivity และไม่มอง label เป็นคุณสมบัติถาวรของ wallet
4. หมวดตลาดจัดด้วยคีย์เวิร์ด มีชื่อที่ตกหล่น การกระจุกกับคู่เทรดสัมพันธ์กับนิยาม score จึงไม่ใช่หลักฐานอิสระ
5. Synthetic evaluation มีข้อจำกัดทั้ง labels, tie-breaking และรูปแบบ injection; ค่า AP/precision@k ที่ต่ำต้องไม่ถูกตัดออก
6. ผลเป็นการเปรียบเทียบเชิงสังเกตของช่วงที่เลือก ไม่ได้พิสูจน์สาเหตุ การสมรู้ร่วมคิด วงแหวน หรือ chip dumping

## 11. สถานะงานและสิ่งที่เหลือ

**เสร็จแล้ว:** preprocessing/validation, baseline Algorithm 1, EDA รอบแรก, lead-in sensitivity, synthetic evaluation, wallet flags, per-market θ-sensitivity, baseline EDA รอบสอง และการวิเคราะห์ครบ 18 weekly windows พร้อมตาราง/กราฟ

**งานที่เหลือสำหรับชุดส่ง:**

- เรียบเรียงรายงานฉบับส่งจากผลที่มี พร้อมอ้างอิงที่มาของอัลกอริทึมและข้อมูล
- ทำสไลด์และวิดีโอ
- ตรวจข้อกำหนดรูปแบบ/ความยาว/ภาษากับ TA ซึ่งเอกสารแผนเดิมยังระบุว่าเป็นข้อสมมติ
- เติมข้อมูลผู้ใช้ใน AI log และตรวจความครบถ้วนของไฟล์ส่ง

หากจะกล่าวอ้างรายละเอียดระดับตลาดหรือวงแหวนเพิ่มเติม ควรตรวจเคสด้วยมือและปรับ/ตรวจการจัดหมวดก่อน ส่วน historical balance validation ยังต้องมีข้อมูลอ้างอิงที่ตรงเวลา จึงต้องระบุเป็นข้อจำกัดหากไม่มีข้อมูลดังกล่าว

## 12. ทางไปยังรายละเอียดและวิธีรัน

| ต้องการดูอะไร | ไฟล์ |
|---|---|
| สถานะ/การตัดสินใจของทีม | [PROGRESS.md](PROGRESS.md) |
| วิธีเตรียมข้อมูลและรัน baseline | [README.md](README.md) |
| วิธีรัน weekly analysis และนิยามตัวชี้วัด | [03_Analytics/weekly/README.md](03_Analytics/weekly/README.md) |
| ข้อค้นพบครบ 18 สัปดาห์ | [03_Analytics/weekly/findings.md](03_Analytics/weekly/findings.md) |
| Evaluation และ EDA รอบสองบน baseline | [03_Analytics/eda/evaluation_findings.md](03_Analytics/eda/evaluation_findings.md) |
| บันทึก AI | [05_AI_Usage_Log/log.md](05_AI_Usage_Log/log.md) |

Parquet รายกระเป๋า/รายตลาดอยู่ในเครื่องและถูก gitignore ตามนโยบายข้อมูลของ repo ส่วนสรุป JSON/CSV, notebook outputs และกราฟใช้สำหรับ review และเรียบเรียงงานส่งได้

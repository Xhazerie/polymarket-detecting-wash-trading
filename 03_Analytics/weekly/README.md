# Weekly analysis

วิเคราะห์ 18 target windows ที่ไม่ทับกัน ครอบคลุม 1 พ.ย.–31 ธ.ค. 2024 และ 1 พ.ค.–30 มิ.ย. 2025 แต่ละช่วงมี 9 windows รวม 61 วัน ใช้ประวัติย้อนหลัง **30 วัน** ตาม `WEEKLY_WINDOWS` เดิม ช่วงสุดท้ายของแต่ละ period มี 5 วัน สัปดาห์ข้ามเดือนเป็นไปตามวันเริ่มที่กำหนด ไม่ใช่ calendar weeks

รันจาก root ของ repo:

```bash
uv run python 04_Evaluation/premise_test/09_weekly_analysis.py
uv run python 03_Analytics/weekly/make_figures.py
```

ค่าเริ่มต้นใช้ DuckDB 8 threads และ memory limit 8 GB ปรับ threads ด้วย `--threads` ได้ รันใหม่เฉพาะ window ด้วย `--windows week_2024-11-01` หรือระบุหลายชื่อได้ ตัวสร้างกราฟต้องมีผลครบทั้ง 18 windows ก่อน

## ผลลัพธ์

- `04_Evaluation/premise_test/results/weekly/windows/*.json`: ผลและ validation แต่ละ window
- `results/weekly/wallet_flags/*.parquet`: คะแนนและธงรายกระเป๋า รวม lead-in (ไฟล์ข้อมูลไม่เข้า git)
- `results/weekly/market_theta/*.parquet`: θ-sensitivity รายตลาด (ไฟล์ข้อมูลไม่เข้า git)
- `results/weekly/daily/*.csv`: สถิติ target trades รายวัน
- `results/weekly/validation.json`: สรุปการตรวจครบทั้งช่วง
- `weekly_summary.csv`, `daily_summary.csv`, `monthly_summary.csv`: ตารางสำหรับใช้ในรายงาน (รายเดือนจัดด้วยวันเทรดจริง แม้ weekly window ข้ามเดือน)
- `weekly_profiles.csv`, `weekly_categories.csv`: เปรียบเทียบ flagged/unflagged
- `weekly_markets.csv`, `top_flagged_markets.csv`: market curves และตลาดที่มี flagged volume สูงสุด
- `adjacent_wallet_transitions.csv`: การเปลี่ยนธงของกระเป๋าที่ active ในสอง windows ติดกัน
- `period_summary.json`: ผลรวมของแต่ละ period และ θ-sensitivity ที่ถ่วงด้วย share volume
- `figures/`: กราฟสรุป และ `findings.md`: ข้อค้นพบหลังรันจริง

## วิธีนับและขอบเขตการตีความ

เรียก shared `score_wallets()` เพียงครั้งเดียวต่อ window แล้วใช้คะแนนชุดเดียวกันสร้าง wallet flags, market curves และ EDA ไม่มีการเปลี่ยน Algorithm 1 หรือ threshold เดิม Trade ถูกติดธงเมื่อ **ทั้งสองกระเป๋า** มี score ≥ θ=0.9 และรายงาน θ=0.70/0.80/0.90/0.95/0.99 ควบคู่กัน

ใช้เฉพาะ `in_target` เมื่อรวม volume ระหว่าง windows จึงไม่รวม lead-in ซ้ำ ผลรวมราย period = ผลรวม flagged share volume ÷ ผลรวม share volume ไม่ใช่ค่าเฉลี่ย percentages รายสัปดาห์ กราฟ volume ใช้หน่วยต่อวันเพื่อเทียบ window 5 วันกับ 7 วัน

คะแนนและธงเป็นผลจากประวัติย้อนหลังรวม target window ของตัวเอง Wallet เดิมอาจเปลี่ยนธงใน window ถัดไป การรวมจำนวนกระเป๋ารายสัปดาห์จึงเป็น **wallet-week observations** ไม่ใช่จำนวนกระเป๋าไม่ซ้ำตลอดสองเดือน Profiles ถ่วงด้วย volume ฝั่งกระเป๋า ซึ่งนับ trade สองฝั่ง และใช้เฉพาะกระเป๋าที่ active ใน target week

หมวดตลาดใช้ keyword rules เดียวกับ EDA รอบสอง ไม่ใช่หมวดทางการ คำว่า unflagged ไม่ได้ยืนยันว่าไม่มี wash และความกระจุกกับคู่เทรดเป็นคำอธิบาย detector ซึ่งใช้ความสัมพันธ์คู่เทรดในการให้คะแนน จึงไม่ใช่ validation อิสระ ผลเชิงสังเกตนี้ยังไม่ยืนยันวงแหวน การสมรู้ร่วมคิด หรือ chip dumping ไม่มีการอ้างว่าช่วงเวลาหรือประเภทตลาดเป็นสาเหตุของความต่าง

Market curves ปัดทศนิยม 4 ตำแหน่งตาม step 08 เดิม ดังนั้น flagged volume ใน `top_flagged_markets.csv` เป็นค่าประมาณ แต่ flagged volume รายสัปดาห์/period ใช้ trade scores โดยตรงก่อนปัด Weekly analysis ไม่ยกเลิกข้อจำกัดเรื่อง position ก่อน lead-in, snapshot `user_position` คนละช่วงเวลา และ synthetic precision/AP ต่ำที่อธิบายไว้ใน `../eda/evaluation_findings.md`

## ตรวจความถูกต้อง

ทุก window ตรวจ score convergence/ขอบเขต/finite values, การคงค่าเฉลี่ย score ถ่วง volume, counts/volume/date boundaries เทียบ extraction เดิม, wallet IDs ไม่ซ้ำ, flag ตรงกับ score, endpoint volume หารสองตรงกับ trade volume และ θ-curves ตรงกับการรวม trades โดยตรง จากนั้นตรวจว่ามี 122 target dates ไม่ซ้ำและผลรวมรายวัน/หมวด/period ตรงกัน

Integration test ใช้ข้อมูลที่ทราบคำตอบ: คู่กระเป๋าที่เปิดแล้วปิด position และคู่ที่เปิดแล้วถือ ตรวจ window 2 วัน การนับ volume สองฝั่ง การจัดหมวด metadata ซ้ำ และผลจาก reused scores เทียบกับ scoring ใหม่:

```bash
uv run python -m unittest discover -s 04_Evaluation/premise_test -p test_weekly_analysis.py
```

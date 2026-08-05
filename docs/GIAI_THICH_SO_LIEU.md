# Mỗi con số trong báo cáo đến từ đâu

*Dùng khi bảo vệ báo cáo. Mỗi mục ghi: **công thức** → **câu lệnh kiểm** → **ví dụ chạy thật**.*

Chạy kiểm bằng: `python analysis/explore.py sql "..."`

---

## 0. Nền tảng: "720 tin" là gì

Bắt đầu từ **1.701 tin** thu thập được. Loại đi:

| Loại đi | Số tin | Vì sao |
|---|--:|---|
| Nhãn nghề = `OTHER` | 882 | Không phải nghề dữ liệu (bán hàng, kế toán, lập trình viên…) |
| Trùng lặp chéo nguồn | 147 | Cùng một tin đăng trên nhiều job board |
| *(giao nhau giữa hai nhóm trên)* | — | |
| **Còn lại** | **720** | Tập phân tích |

Điều kiện lọc được viết **một lần duy nhất** trong code (`pipeline/utils/analysis_base.py`) và mọi phân
tích đều import nó — để không xảy ra chuyện hai bảng dùng hai mẫu số khác nhau.

```sql
-- kiểm: phải ra 720
SELECT COUNT(*) FROM jobs_silver
WHERE job_family IS NOT NULL AND job_family <> 'OTHER'
  AND is_active AND is_duplicate_of IS NULL;
```

---

## 1.1. Thị phần theo nhánh — *Analytics 46,9%*

**Công thức:** đếm số tin của mỗi nhánh, chia cho 720.

```sql
SELECT jf_domain, COUNT(*) n, ROUND(100.0*COUNT(*)/720, 1) pct
FROM jobs_silver WHERE <điều kiện 720> GROUP BY 1 ORDER BY n DESC;
```

Analytics 338 tin → 338/720 = **46,9%**. Data Scientist 31 tin → 31/720 = **4,3%**.

Bảng `gold_domain_share` đã tính sẵn kết quả này.

---

## 1.2. Bốn nghề lớn nhất — *BA 146 · DE 125 · AIE 110 · DA 105*

Cùng cách trên nhưng nhóm theo `job_family` thay vì `jf_domain`. Bảng `gold_market_share`.

**Vì sao nói "ngang nhau, đừng xếp hạng":** với 720 tin, sai số chuẩn của một tỉ lệ khoảng 15--20% là
**±3 điểm phần trăm**. BA 20,3% và DE 17,4% chênh 2,9pt — nhỏ hơn sai số, nên không kết luận được cái
nào lớn hơn. Giống thăm dò bầu cử "45% ± 3%".

---

## 1.3. Kỹ năng phổ biến — *SQL 47,8%*

**Công thức:** số tin **có nhắc** kỹ năng đó, chia cho 720. Một tin có 8 kỹ năng thì được đếm ở cả 8
dòng — đây là "% tin yêu cầu X", không phải "tỉ trọng trong tổng số kỹ năng".

```sql
SELECT skill, SUM(n) n, ROUND(100.0*SUM(n)/720, 1) pct
FROM gold_family_skill GROUP BY 1 ORDER BY n DESC LIMIT 10;
```

SQL 344 tin → **47,8%**.

⚠️ Kỹ năng lấy từ **từ điển chuẩn hoá** (`ref/skills_dictionary.yml`), đối chiếu cả tag có sẵn của job
board lẫn toàn văn mô tả. Kỹ năng chưa có trong từ điển thì **không được đếm** — danh sách ở
`data/quality/unmapped_skills.csv`.

---

## 1.4. Tiếng Anh theo ngành — *công nghệ 48,8% vs e-commerce 16,7%*

**Công thức:** trong mỗi ngành, số tin có kỹ năng `English` chia cho tổng số tin của ngành đó.

```sql
SELECT company_type, COUNT(*) n,
       ROUND(100.0*SUM(CASE WHEN skills LIKE '%English%' THEN 1 ELSE 0 END)/COUNT(*), 1) pct_english
FROM jobs_silver WHERE <điều kiện 720>
GROUP BY 1 HAVING n >= 25 ORDER BY pct_english DESC;
```

Công nghệ: 103/211 = **48,8%**. Thương mại điện tử: 5/30 = **16,7%**.

Chỉ lấy ngành có **≥25 tin** — dưới mức đó thì một tin đổi cũng làm tỉ lệ nhảy vài điểm.

---

## 1.5. Remote — *4,9%*

```sql
SELECT SUM(CASE WHEN remote_flag THEN 1 ELSE 0 END) remote, COUNT(*) tong
FROM jobs_silver WHERE <điều kiện 720>;
```

35/720 = **4,9%**. Cột `remote_flag` do tầng chuẩn hoá suy ra từ trường địa điểm và mô tả.

---

## 1.6. Hà Nội vs TP.HCM

Bảng chéo `city × jf_domain`, mỗi thành phố chia cho tổng tin **của thành phố đó** (không chia cho 720).

Hà Nội 325 tin, trong đó Analytics 148 → 45,5%. TP.HCM 303 tin, Analytics 151 → 49,8%.

*(67 tin không ghi thành phố, không nằm trong phép so sánh này.)*

---

## 2.1. Số kỹ năng theo cấp bậc — *Junior 8,2 vs Mid 9,8*

**Công thức:** trung bình cộng của `n_skills` (số kỹ năng của một tin), nhóm theo cấp bậc.

```sql
SELECT seniority, COUNT(*) n, ROUND(AVG(n_skills), 1) trung_binh, MEDIAN(n_skills) trung_vi
FROM jobs_silver WHERE <điều kiện 720> GROUP BY 1;
```

⚠️ **Con số "15% tin Junior nhắc 2--3 năm kinh nghiệm" yếu hơn các số khác.** Nó đếm bằng cách tìm chuỗi
`"2 year"`, `"3 năm kinh nghiệm"`… trong mô tả — tức khớp từ khoá thô, không phân biệt được
*"yêu cầu 2 năm"* với *"công ty có 2 năm kinh nghiệm trong ngành"*. Dùng nó như **dấu hiệu**, đừng dùng
như số đo chính xác.

---

## 2.2 & 2.3 & 3.2. Bản đồ chuyển nghề ⭐ phần cần giải thích kỹ nhất

### Bước 1 — Định nghĩa "hồ sơ kỹ năng" của một nghề

Kỹ năng xuất hiện ở **≥25%** số tin của nghề đó.

### Bước 2 — Ô (hàng A, cột B) = *A đã có bao nhiêu % hồ sơ của B*

$$\text{ô}(A \rightarrow B) \;=\; \frac{|\,\text{hồ sơ}(A) \cap \text{hồ sơ}(B)\,|}{|\,\text{hồ sơ}(B)\,|}$$

### Ví dụ chạy thật: `Data Analyst → BI`

**Hồ sơ Data Analyst — 12 kỹ năng:**
Data Analysis 80% · SQL 69% · Reporting 66% · Power BI 62% · Python 43% · Statistics 41% ·
Tableau 38% · Excel 37% · Data Management 32% · Data Visualization 32% · Database 29% · English 28%

**Hồ sơ BI — 9 kỹ năng:**
Power BI 88% · Reporting 84% · SQL 72% · Data Analysis 67% · Business Intelligence 49% ·
Python 35% · Tableau 35% · Data Modeling 26% · Excel 26%

**Giao nhau — 7 kỹ năng:** Data Analysis, Excel, Power BI, Python, Reporting, SQL, Tableau
**BI có mà DA chưa có — 2:** Business Intelligence, Data Modeling

$$\text{DA} \rightarrow \text{BI} \;=\; \frac{7}{9} \;=\; \mathbf{77{,}8\%}
\qquad\qquad
\text{BI} \rightarrow \text{DA} \;=\; \frac{7}{12} \;=\; \mathbf{58{,}3\%}$$

### Vì sao hai chiều khác nhau — và vì sao đó là phát hiện

**Tử số giống hệt nhau (7 kỹ năng chung), chỉ mẫu số đổi.** Nghề đòi *nhiều* kỹ năng thì "bao" được nghề
đòi *ít*; chiều ngược lại thì không.

Đó chính là ý nghĩa của câu **"thang chỉ đi một chiều"**: Data Engineer có hồ sơ dày (24 kỹ năng) nên đã
sẵn 58% hồ sơ Data Analyst; Data Analyst hồ sơ mỏng hơn nên chỉ có 29% hồ sơ Data Engineer.

Và **"Business Analyst dễ vào khó ra"** cũng từ đây: hồ sơ BA rất mỏng, nên ai cũng bao được nó, còn nó
thì không bao được ai.

### Kiểm bằng lệnh

```bash
python analysis/career_map.py          # sinh lại toàn bộ bảng
```
Kết quả: `analysis/outputs/career_map_matrix.csv` · `docs/CAREER_MAP_FINDINGS.md`

### ⚠️ Giới hạn quan trọng: ngưỡng 25% là do người chọn

Script tự chạy lại với 20% / 25% / 30% và chia kết quả làm hai loại:

| Loại | Cách dùng |
|---|---|
| Dao động **≤15 điểm** qua cả ba ngưỡng | Được trích **con số cụ thể** |
| Dao động lớn hơn | **Chỉ nói theo hướng** ("gần / xa"), không trích số |

`Data Analyst → Risk/Fraud` là **83%** và **bền** (90/83/75 qua ba ngưỡng) ⇒ trích được.
`Data Analyst → BI 78%` thì **không bền** ⇒ chỉ nói "hai nghề này rất gần nhau".

---

## 2.4. Kỹ năng của AI Engineer — *SQL chỉ 25,5%*

**Công thức:** trong 110 tin AI Engineer, bao nhiêu tin nhắc kỹ năng đó.

```sql
SELECT skill, share_in_family FROM gold_family_skill
WHERE job_family = 'AI_ENGINEER' ORDER BY share_in_family DESC;
```

LLM 69,1% · API 56,4% · Cloud 38,2% · Docker 33,6% · **SQL 25,5%**.

**Điểm mấu chốt:** SQL ở toàn thị trường là **47,8%**, nên 25,5% là **thấp hơn mặt bằng**, không phải
"chỉ hơi ít". Đó là điều làm phát hiện này đáng nói.

---

## 2.5. Lift — *Python ×0,99, Power BI ×2,53* ⭐ khái niệm quan trọng thứ hai

**Công thức:**

$$\text{lift} \;=\; \frac{\%\ \text{tin của nghề X có kỹ năng A}}{\%\ \text{toàn thị trường có kỹ năng A}}$$

**Đọc:** `> 1` = đặc trưng của nghề đó · `≈ 1` = phổ biến khắp nơi, không nói lên gì · `< 1` = nghề đó
dùng **ít hơn** bình thường.

**Ví dụ Data Analyst:**

| Kỹ năng | % trong DA | % thị trường | lift |
|---|--:|--:|--:|
| Tableau | 38,1% | 12,8% | **2,98** |
| Excel | 37,1% | 14,6% | **2,54** |
| Power BI | 61,9% | 24,4% | **2,53** |
| Statistics | 41,0% | 16,3% | **2,52** |
| **Python** | **42,9%** | **43,5%** | **0,99** |

**Python có mặt ở 43% tin Data Analyst — nghe rất nhiều. Nhưng nó cũng có mặt ở 43% toàn thị trường,
nên nó không phân biệt được gì.** Đây là lý do phải dùng lift chứ không dùng tần suất trần.

```sql
WITH mkt AS (SELECT skill, SUM(n)*1.0/720 p FROM gold_family_skill GROUP BY 1)
SELECT g.skill, g.share_in_family, ROUND(g.share_in_family/100.0/m.p, 2) lift
FROM gold_family_skill g JOIN mkt m USING (skill)
WHERE g.job_family = 'DATA_ANALYST' AND g.share_in_family >= 25
ORDER BY lift DESC;
```

---

## 2.6. Ngành × nghề — *công nghệ tuyển AI 53 vs ngân hàng 19*

Bảng chéo, đếm thuần:

```sql
SELECT company_type, job_family, COUNT(*) n
FROM jobs_silver WHERE <điều kiện 720>
  AND company_type IN ('tech_software', 'bank_finance')
GROUP BY 1, 2 ORDER BY 1, n DESC;
```

Ngân hàng "độc chiếm" Risk/Fraud: **29/38 tin** của nhánh đó đến từ ngân hàng (không phải 29/205).
Data Governance: **14/27**.

⚠️ Chênh lệch này **một phần là hiệu ứng job board** — mỗi nền tảng thiên về một loại doanh nghiệp khác
nhau. Nói theo hướng thì an toàn, nói theo con số "gấp 3 lần" thì phải kèm cảnh báo.

---

## 3.1. Bộ kỹ năng tối thiểu — ngưỡng **50%**

Kỹ năng xuất hiện ở **hơn một nửa** số tin của nghề đó.

```sql
SELECT skill, share_in_family FROM gold_family_skill
WHERE job_family = 'DATA_ANALYST' AND share_in_family >= 50
ORDER BY share_in_family DESC;
```

**Vì sao ngưỡng này khác ngưỡng của ma trận (25%)?** Hai mục đích khác nhau:

| Ngưỡng | Dùng cho | Lý do |
|---|---|---|
| **≥50%** | "Cần gì để ứng tuyển" | Danh sách ngắn, dứt khoát — thứ *phần lớn* tin đòi |
| **≥25%** | "So sánh hai nghề" | Ở mức 50% hồ sơ co lại còn 1–6 kỹ năng, ma trận thành vô nghĩa (Business Analyst chỉ còn **đúng 1** kỹ năng ⇒ mọi ô liên quan hoá 0% hoặc 100%) |

Đây là chỗ dễ nhầm nhất — **đừng trộn hai ngưỡng khi trình bày.**

---

## 4. Con số chất lượng nhãn — *96,7% và 86,2%*

**Nhãn nghề — 29/30 = 96,7%.** Lấy mẫu phân tầng 30 tin, người gán nhãn **ẩn hoàn toàn đáp án của máy**
(ẩn cột trong Excel), quyết định xong mới đối chiếu. File: `data/labeling/spot_check.csv`.

Khoảng tin cậy 95% là **83,3%--99,4%** — rộng vì n=30 nhỏ. Phải nói kèm.

**Cấp bậc — 86,2% đúng bậc.** Hai mô hình ngôn ngữ độc lập đọc *chỉ tiêu đề + mô tả*, không thấy nhãn
của hệ thống. Chỉ những tin mà **cả hai giám định đồng thuận với nhau** mới được dùng làm tham chiếu
(n=65). Script: `analysis/audit_seniority.py`.

---

## 5. Ba câu hỏi thầy có thể hỏi — và câu trả lời

**"Sao biết 720 tin này đại diện cho thị trường?"**
→ *Không đại diện, và báo cáo nói rõ điều đó.* Mỗi job board được tìm bằng bộ từ khoá khác nhau nên cơ
cấu khác nhau rất xa (Analytics 25,5% ở Glints, 60,4% ở VietnamWorks). Mọi phát biểu đều mở đầu bằng
*"trong 720 tin thu thập được"*.

**"Kỹ năng lấy từ đâu, có bỏ sót không?"**
→ Từ từ điển chuẩn hoá, đối chiếu cả tag của job board lẫn toàn văn mô tả. **Có bỏ sót**, và phần bỏ sót
được ghi lại ở `data/quality/unmapped_skills.csv`. Chính nhờ đọc file này mà 7 kỹ năng bị đếm thiếu
(Business Analysis, Database, Cloud…) được phát hiện và bổ sung.

**"Ngưỡng 25% và 50% chọn kiểu gì?"**
→ Do người chọn, và **đã kiểm độ nhạy**: script chạy lại với ba ngưỡng, kết luận nào đổi nhiều thì chỉ
được nói theo hướng chứ không được trích số. Chi tiết trong `docs/CAREER_MAP_FINDINGS.md`.

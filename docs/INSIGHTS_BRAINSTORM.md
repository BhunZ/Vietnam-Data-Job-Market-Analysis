# Insight để brainstorm cho báo cáo môn Data Analyst

*Cập nhật: 26/07/2026 · analysis base **720** tin Data/AI · nguồn số: `gold_*` trong
`data/warehouse.duckdb` + `analysis/outputs/*.csv`.*

> **Vì sao base là 720 chứ không phải 752 như bản trước:** khâu khử trùng lặp gom theo `company_key`,
> nhưng một nhà tuyển dụng viết nhiều kiểu thì thành nhiều key — MB Bank từng là **4 key / 91 tin**
> (`NGÂN HÀNG TMCP QUÂN ĐỘI – MBBANK`, `MBBANK`, `MB Bank`, `Ngân Hàng TMCP Quân Đội`), nên các tin
> đăng chéo trên topcv/topdev/vietnamworks **không bị khử**. Sau khi gộp alias thương hiệu, số tin
> trùng phát hiện được tăng **112 → 147** và base giảm 752 → 720. Con số 720 mới là đúng.

> **Cách dùng file này.** Mỗi insight có: **Phát hiện** (số liệu) → **Ý nghĩa** (diễn giải) → **Bằng
> chứng** (bảng/file để trích dẫn). Nhóm A dùng làm luận điểm chính; nhóm B cần nêu kèm giới hạn; nhóm C
> là insight *về phương pháp* — thường là phần được điểm cao nhất ở môn DA nhưng ít ai làm.
>
> **Sai số cần nhớ:** với n≈720, sai số chuẩn của một tỉ lệ ~15% là **±1,3 điểm phần trăm**. Hai con số
> chênh nhau dưới ~3pt thì **không kết luận cái nào lớn hơn**.

---

## Nhóm A — Vững, dùng làm luận điểm chính

### A1. Thị trường Data Việt Nam là thị trường *phân tích nghiệp vụ*, không phải *nghiên cứu mô hình*

**Phát hiện.** Chia theo 3 nhánh chính: **Analytics 46,9%** (338 tin) · **AI/ML 24,9%** (179) ·
**Data Engineering 20,1%** (145) · Governance & Architecture 5,6% (40) · Data Leadership 2,5% (18).
Trong khi đó các vai trò mô hình hoá thuần rất mỏng: Data Scientist ~4%, ML Engineer ~1%,
Research Scientist <1%.

**Ý nghĩa.** Nghịch lý đáng nói: truyền thông nói về AI, nhưng gần **một nửa** nhu cầu thật là người
*biến dữ liệu thành quyết định*. Với người mới, cửa vào xác suất cao nhất là Analytics — không phải
Data Science.

**Bằng chứng.** `gold_domain_share` · `analysis/figures/domain_share.png`.
Đây là cấp **ổn định hơn** cấp family khi đổi judge (chênh 20+pt, xem C1).

⚠️ **Đính chính (2026-07-28).** Bản trước của mục này viết cấp domain là "xếp hạng an toàn". Điều đó
**không đúng**: cấp domain ổn định trước việc *đổi judge*, nhưng **không** ổn định trước *thành phần job
board*. Tỉ lệ Analytics theo từng nguồn: vietnamworks **60,4%** · topcv 53,8% · careerviet 50,9% ·
topdev 47,8% · itviec 28,9% · glints **25,5%** — dao động 35pt. Và tỉ lệ tin lọt vào base cũng lệch theo
nguồn (topcv 91,9% · glints 82,3% · itviec 66,4% · vnw 32,3% · careerviet 28,8% · topdev 28,0%), cả hai đều
là hàm của độ rộng truy vấn scrape từng board.

Vì VietnamWorks đóng góp **255/720** tin base, con số 46,9% chủ yếu là **profile của VietnamWorks pha
loãng**. Cách phát biểu đúng: *"trong 720 tin đã thu thập được, Analytics chiếm 46,9%"* — **không** phải
*"thị trường Data Việt Nam có 46,9% là Analytics"*. Bảng đầy đủ ở
`analysis/market_insights_report.md` §6.1.

### A2. Business Analyst không có "dấu vân tay" công cụ nào

**Phát hiện.** Xét skill đặc trưng (lift = mức vượt trội so với toàn thị trường):

| Nhánh | Skill đặc trưng nhất |
|---|---|
| Data Engineer | ELT 39% (**x4,4**) · Airflow 32% (x3,9) · Spark 42% (x3,8) · Data Lake 33% (x3,6) |
| AI Engineer | NLP 35% (**x5,1**) · Computer Vision 32% (x4,9) · LLM 69% (x4,3) · PyTorch 32% (x4,1) |
| Data Analyst | Data Visualization 33% (**x3,0**) · Tableau 40% (x2,8) · Excel 37% (x2,6) · Power BI 62% (x2,5) |
| **Business Analyst** | **cao nhất chỉ x1,2** (Tiếng Anh); Data Analysis x1,0; Reporting **x0,9** |

**Ý nghĩa.** BA được định nghĩa bằng **ngữ cảnh nghiệp vụ**, không bằng công cụ. Ba hệ quả để bàn:
(a) đây là nhánh **khó tự học nhất** qua khoá học công cụ; (b) nó cũng là nhánh **khó tuyển đúng nhất**;
(c) và nó giải thích luôn vì sao máy phân loại hay nhầm BA — không có tín hiệu kỹ năng để bám vào.

**Bằng chứng.** `gold_family_skill` (share_in_family) chia cho tỉ lệ toàn thị trường ·
`analysis/figures/skill_dna.png`.

### A3. Cửa vào nghề rất hẹp — nhưng hẹp không đều giữa các nhánh

**Phát hiện.** Toàn thị trường: Mid 33,3% · Senior 30,0% · **Junior 17,4%** · Manager 8,3% · Lead 7,6% ·
Intern 2,6% · Không xác định chỉ còn **0,7% (5 tin)**. Chia theo nhánh (Junior+Intern trên tổng nhánh):

| Nhánh | Junior+Intern | Tỉ lệ |
|---|--:|--:|
| AI / Machine Learning | 47/179 | **26,3%** |
| Analytics | 70/338 | 20,7% |
| Governance & Architecture | 6/40 | 15,0% |
| **Data Engineering** | **21/145** | **14,5%** |
| Data Leadership | 0/18 | 0% |

**Ý nghĩa.** **Data Engineering là nhánh khó vào nhất** (14,5%) — hợp lý vì nó đòi hạ tầng/production.
Nghịch lý thú vị: **AI/ML lại dễ vào nhất** (26,3%, gần gấp đôi DE) dù nghe "cao cấp" hơn — có thể vì đây
là mảng mới, doanh nghiệp chấp nhận tuyển người trẻ rồi đào tạo. Thứ tự này **không đổi** qua cả bốn lần
sửa cách đo bên dưới, nên nó là kết luận bền nhất trong mục này.

⚠️ **Đọc con số "cửa vào hẹp" một cách thận trọng.** Junior+Intern đã đi 5,6% → 11,7% → 21,9% → **20,0%**
qua bốn lần sửa CÁCH ĐO, trong khi dữ liệu không đổi một dòng: bỏ `default: Mid`, đọc số năm trong JD, đọc
**trường số năm có cấu trúc**, rồi (lần cuối) coi trường đó là **sàn chứ không phải yêu cầu**. Bài học:
"cửa vào rất hẹp" ở bản đầu phần lớn là **hiện vật đo lường**, không phải sự thật thị trường — và chiều
dịch chuyển không phải lúc nào cũng cùng hướng.

**Bằng chứng.** `gold_seniority` · `analysis/figures/seniority_share.png`.
Nguồn suy luận (cột `seniority_source`, 5 mức — **đừng gộp chúng lại**):

| Nguồn | n | Đây là gì |
|---|--:|---|
| `rule_title` | 342 | từ khoá cấp bậc trong **tiêu đề** / nhãn cấp bậc của site — bằng chứng mạnh nhất |
| `rule_years_source` | 183 | **trường số năm có cấu trúc** do nguồn tự khai (VNW `years_of_experience`, TopCV `monthsOfExperience`, Glints `min_years_exp`) |
| `rule_years_jd` | 161 | số năm **parse từ văn xuôi JD** |
| `llm` | 29 | LLM đọc JD và trích câu làm bằng chứng |
| `none` | 5 | tin thật sự không nêu gì |

Ba mức đầu từng bị gộp thành một chữ `rule`, che mất việc **22% giá trị đến từ regex trên văn xuôi JD** —
đúng loại đầu vào mà thiết kế đã cố ý loại khỏi việc khớp pattern. Xem C3.

**Cột `seniority_source` này đã được kiểm định mù** — xem A3b.

### A3b. Cấp bậc đã được KIỂM ĐỊNH MÙ — và tầng bằng chứng "trông đáng tin nhất" lại là tầng yếu nhất

Đây là mục nên đưa vào báo cáo như một **phần phương pháp**, không phải phát hiện thị trường: nó cho thấy
con số ở A3 đáng tin tới đâu.

**Cách kiểm định.** `analysis/audit_seniority.py` lấy mẫu **phân tầng theo `seniority_source`** (mỗi tầng
30 tin) rồi đưa cho **hai LLM độc lập** chỉ thấy *tiêu đề + JD* — **không** thấy nhãn của ta. Chỉ những tin
mà **hai auditor tự đồng thuận với nhau** được dùng làm tham chiếu; hai auditor này (`cerebras`, `mistral`)
**không** quyết định bất kỳ giá trị nào ở tầng `llm`, nên audit độc lập cả trên tầng đó.

| Nguồn | n | Khớp đúng | Lệch ≤1 bậc |
|---|--:|--:|--:|
| `rule_title` | 22 | **90,9%** | 100% |
| `rule_years_jd` | 22 | **90,9%** | 100% |
| `llm` | 10 | 80,0% | 90,0% |
| `rule_years_source` | 11 | **72,7%** | 90,9% |
| **Toàn mẫu** | **65** | **86,2%** | **96,9%** |

**Điều bất ngờ — và là điểm đáng kể nhất để kể trong báo cáo.** Thiết kế ban đầu giả định thứ tự tin cậy
là *tiêu đề > trường số năm do site tự khai > regex trên văn xuôi JD*. Audit cho kết quả **ngược ở hai vế
sau**: trường có cấu trúc (72,7%) **kém hơn** regex trên JD (90,9%). Nguyên nhân đã truy được: **trường
"số năm kinh nghiệm" trên form tuyển dụng là một cái SÀN, không phải yêu cầu thật.** Trong 261 tin có cả
hai tín hiệu, 29 tin lệch bậc, và 11/12 tin lấy mẫu có trường form **thấp hơn** JD — ví dụ một tin
*AI Engineer* khai `years_of_experience = 1` trong khi JD viết *"Own at least one client's AI system
end-to-end"* và auditor đọc ra Senior.

**Hai lỗi đã sửa từ audit này:**

1. **Trường form là sàn** → khi cả hai tín hiệu tồn tại, **bậc cao hơn thắng** (cả hai chiều).
2. **Từ chỉ cấp bậc viết liền.** `"Data Analyst Teamleader"` — khớp theo biên từ (`\bleader\b`) không thấy
   `leader` nằm trong `Teamleader`, nên tiêu đề bị bỏ qua và tin Lead này bị gán **Junior** theo số năm.

**Kiểm chứng ghép cặp (paired) sau khi sửa.** Mẫu phân tầng không đo được hiệu quả của fix, vì fix **chuyển
tin giữa các tầng** và auditor thì đã cạn quota (49/124 tin thiếu phiếu). Nên phép kiểm đúng là: lấy **32
tin mà fix đã đổi nhãn**, chấm nhãn *cũ* và nhãn *mới* trên **cùng tập tin, cùng phiếu auditor đã cache**:

| | Khớp đúng | Tổng khoảng cách bậc |
|---|--:|--:|
| Nhãn **cũ** (trước fix) | 0/5 | 7 |
| Nhãn **mới** (sau fix) | **5/5** | **0** |

⚠️ **n=5** (chỉ 5 trong 32 tin đổi nhãn có hai auditor đồng thuận) — quá nhỏ để tuyên bố một tỉ lệ chính
xác. Điều nó cho phép nói là: **không có tin nào fix làm xấu đi**, và chiều dịch chuyển khớp với cơ chế đã
truy được độc lập (11/12 mẫu có form thấp hơn JD). Đừng viết "độ chính xác tăng lên 100%".

**Ý nghĩa để viết vào báo cáo.** Cấp bậc **không** phải một trường có sẵn trong dữ liệu — nó là một trường
**suy luận**, và cột `seniority_source` cho phép nói *mỗi con số đến từ đâu và tầng đó chính xác bao nhiêu*.
Với `Unknown` chỉ còn 0,7%, hạn chế thật sự của phân bố A3 không phải là độ phủ mà là **~14% sai bậc**,
tập trung ở tầng tự khai của nhà tuyển dụng.

**Bằng chứng.** `analysis/outputs/seniority_audit.csv` · `analysis/audit_seniority.py`
(`--cached-only` để tái lập báo cáo không tốn quota) · `tests/test_derived_fields.py` (mỗi lỗi trên được
ghim bằng một test).

### A4. Ngân hàng/Tài chính là nhà tuyển dụng Data lớn nhất — hơn cả công ty công nghệ

**Phát hiện.** Ngân hàng/Tài chính **199 tin (27,6%)** vs Công nghệ/Phần mềm **176 tin (24,4%)** — hai
khối gần bằng nhau, chênh 3,2pt nên **không kết luận dứt khoát cái nào lớn hơn** (bản trước chênh 5,4pt
và tôi đã kết luận quá mạnh).
Ngân hàng tuyển **toàn phổ**, không chỉ risk: BA 37 · Data Engineer 37 · Risk/Fraud 29 · Data Analyst 21 ·
AI Engineer 18 · Data Governance 12.
Ngược lại, **29/38 tin Risk/Fraud Analyst (76%) đến từ ngân hàng** — gần như độc quyền một nhánh nghề.

**Ý nghĩa.** Ai muốn vào ngành data ở VN thì **ngân hàng là cửa lớn nhất**, không phải công ty tech.
Điều này cũng lý giải vì sao `Data Governance` tồn tại như một nhánh riêng (16 tin từ ngân hàng) — đó là
áp lực tuân thủ của ngành tài chính, không phải nhu cầu tự nhiên của thị trường.

**Bằng chứng.** `gold_company` · `analysis/figures/industry_share.png`.
⚠️ **14,4% tin chưa phân loại được ngành** → mọi tỉ lệ ngành là "trong số đã nhận dạng được", phải nói
rõ mẫu số. Nguồn (cột `company_type_source`): **464 tin từ tên công ty** (rule) · **152 tin từ LLM**
(2 judge phải đồng thuận về thương hiệu; bất đồng → giữ `unknown`) · **104 tin vẫn chưa rõ**. Phần dư là
**đuôi dài công ty nhỏ/vô danh** (gần như mỗi công ty 1 tin) — LLM đã **chủ động trả lời "không biết"**
thay vì đoán (`Sunteco`, `Slimcase`, `DENIS G.M.`).

### A5. Tiếng Anh là kỹ năng đứng thứ 5 — cao hơn Power BI

**Phát hiện.** Lõi kỹ năng: SQL 47,8% · Python 43,5% · Data Analysis 39,6% · Reporting 38,3% ·
**Tiếng Anh 33,8%** · Machine Learning 30,4% · Power BI 24,4%.

**Ý nghĩa.** Một kỹ năng **phi kỹ thuật** nằm trong top 5 — rào cản ngôn ngữ là thật và định lượng được.
Với BA thì Tiếng Anh còn là **skill đặc trưng duy nhất** (x1,2, xem A2).

**Bằng chứng.** `skill_demand`.

---

## Nhóm B — Tốt, nêu kèm giới hạn

### B1. SQL là trục trung tâm của mọi lộ trình học

**Phát hiện.** Các cặp kỹ năng đồng xuất hiện nhiều nhất: Python+SQL 219 tin · Reporting+SQL 185 ·
Data Analysis+SQL 184 · Data Analysis+Reporting 169 · Machine Learning+Python 168 · Power BI+SQL 154.
SQL ghép cặp mạnh nhất với gần như mọi kỹ năng khác.

**Ý nghĩa (lộ trình).** Nền **SQL + Python** trước, rồi rẽ nhánh theo đích:
`+Power BI/Tableau/Excel` → Data Analyst · `+Spark/Airflow/ELT` → Data Engineer ·
`+ML/LLM/PyTorch` → AI Engineer.

**Bằng chứng.** `analysis/outputs/association_rules.csv` (chỉ trích các luật có
`significant_bonferroni = True` — **1244/1649**, alpha = 0,05/4060 giả thuyết đã test). Cột
`significant_at_kept_alpha` giữ ngưỡng cũ 0,05/1649 (quá lỏng, cho 1299 luật) — **đừng dùng cột đó để
trích dẫn**. Mỗi cặp 1-1 xuất hiện hai chiều nên số dòng KHÔNG phải số phát hiện.

### B2. Có những "combo đi liền" — học lẻ một nửa gần như vô nghĩa

**Phát hiện.** Các luật lift rất cao mà **vẫn qua kiểm định Bonferroni**:

| Luật | Số tin | Confidence | Lift |
|---|--:|--:|--:|
| TensorFlow ↔ PyTorch | 57 | 0,98 | **x10,8** |
| Big Data + Spark → Hadoop | 32 | 0,64 | x10,5 |
| Kubernetes + Python → Docker | 36 | 0,88 | x7,5 |
| Hadoop → Spark | 37 | 0,93 | x7,3 |

**Ý nghĩa.** Đây là các "bộ đôi bắt buộc" của một ngăn xếp công nghệ. Nếu học TensorFlow mà không biết
PyTorch (hoặc ngược lại), gần như chắc chắn lệch so với yêu cầu tin tuyển dụng.

**Giới hạn.** Đây là đồng-xuất-hiện, **không phải nhân quả** và **không nói học cái nào trước**.

### B3. Hà Nội nhiều tin Data hơn TP.HCM — và lệch mạnh về Governance

**Phát hiện.** Hà Nội 357 tin vs TP.HCM 303. Chia theo nhánh:
Governance & Architecture **HN 31 vs HCM 12** (gấp 2,6 lần); Data Engineering HN 75 vs HCM 57;
Analytics HN 167 vs HCM 151; AI/ML gần bằng nhau (77 vs 73).

**Ý nghĩa.** Trái trực giác "HCM là trung tâm kinh tế". Giả thuyết để bàn: **trụ sở ngân hàng tập trung
ở Hà Nội**, và Governance là nhu cầu đặc thù của ngành tài chính (khớp với A4).

**Giới hạn.** Phụ thuộc độ phủ của từng job board; 1 snapshot.

### B4. Chủ đề JD ẩn: database là một mảng riêng, không nằm trong "data engineering"

**Phát hiện.** Topic modeling (NMF, k=9 chọn theo NPMI coherence) cho ra 7 topic diễn giải được, trong đó
có một topic **thuần database** mà bảng thị phần không thể hiện: `oracle · sql server · mysql ·
postgresql · mongodb` (45 tin). Các topic còn lại: AI/ML (129) · data warehouse-lake (82) ·
risk/ngân hàng tiếng Việt (65) · business analyst-agile (62) · BI tooling (53).

**Ý nghĩa.** Có một lớp nhu cầu **vận hành cơ sở dữ liệu truyền thống** tồn tại song song với data
engineering hiện đại (Spark/Airflow/lake). Bảng `job_family` gộp chúng, topic model tách ra được.

**Giới hạn.** 2/9 topic bị gắn cờ `interpretable = False` (boilerplate của nhà tuyển dụng còn sót) →
**không diễn giải 2 topic đó**, đã loại khỏi phần trên.

---

## Nhóm C — Insight về phương pháp (điểm cộng lớn nhất cho môn DA)

### C1. "Nhãn" là một biến có sai số, không phải sự thật

**Phát hiện.** Trên **cùng corpus, cùng prompt**, chỉ đổi thành phần LLM judge: Data Engineer dịch
**158 → 119 tin** và **nhánh đứng đầu bị lật**. Sửa câu prompt (v2 → v3) làm đổi **~13% toàn bộ nhãn**.
Các judge khác nhau hệ thống về mức độ sẵn sàng gán `OTHER`: 61% (Llama-3.1-8B) vs 77% (gpt-oss-120B).

**Ý nghĩa.** Vì vậy báo cáo **phải dẫn bằng cấp domain** (chênh 20+pt nên vững) và **không xếp hạng
cấp family**. Đây là bài học đo lường thật: đừng trình bày đầu ra của một mô hình như dữ liệu quan sát.

### C2. Một tầng "tối ưu hoá" có thể âm thầm phá dữ liệu

**Phát hiện (2 ca thật trong dự án này).**
1. Bộ lọc boilerplate của topic modeling chạy theo *từng dòng*, nhưng 5/6 nguồn lưu JD thành **một
   dòng duy nhất** → **356/752 tin (47,3%) mất TOÀN BỘ mô tả công việc** (itviec và topcv mất 100%).
   Hệ quả: model "đọc" lại chính skill tag, và topic tách theo **website nguồn + ngôn ngữ** thay vì
   theo chủ đề.
2. Tầng embedding gán nhãn **không có prototype cho "không phải job data"** → nó buộc phải chọn một
   nhánh data cho *mọi* tin. Kết quả thật: *Giáo viên STEM-AI Robotics* → AI Engineer;
   *Software Engineer* → Big Data Engineer.

**Ý nghĩa.** Tầng rẻ phải **hẹp**, không chỉ **rẻ**. Một bước tiền xử lý sai có thể vô hiệu hoá cả một
deliverable mà không báo lỗi nào.

### C3. Giá trị mặc định là kẻ nói dối tinh vi nhất

**Phát hiện.** File cấu hình seniority **không có pattern nào cho "Mid"** nhưng đặt `default: Mid` →
**339/752 tin (45,1%)** không khớp gì cả và bị gán "Mid" âm thầm. "Mid 54%" thực chất là
*"Mid 54%, trong đó 45pt là KHÔNG BIẾT"*, và nó làm tỉ lệ Junior thấp trông như một phát hiện thị trường.
Tương tự, phân loại ngành khớp cả **300 ký tự đầu JD**, nên 49% ca được phân loại *chỉ vì chữ trong tin*:
`POLYTEX FAR EASTERN` (dệt) → ngân hàng; `Dai-ichi Life` (bảo hiểm) → outsourcing.

**Sau khi sửa:** Junior **51 → 208 tin** (đọc số năm kinh nghiệm thật), và `Unknown` được báo cáo công
khai 19,3% thay vì trộn vào Mid.

**Ý nghĩa.** Luôn hỏi: *"con số này là **đo được** hay là **mặc định**?"* Và: một thuộc tính của **nhà
tuyển dụng** phải suy ra từ nhà tuyển dụng, không từ nội dung tin.

### C4. Không có "cụm nghề tự nhiên" — và đó là một kết quả, không phải thất bại

**Phát hiện.** Silhouette dao động **0,133–0,203 qua toàn bộ k = 2..20** (dưới 0,25 = *không có cấu trúc
cụm đáng kể*); argmax rơi vào k=18 tức **mép khoảng tìm kiếm**. Cụm tách "tốt nhất" (silhouette 0,459)
lại là cụm chỉ có **1,8 skill/tin** — nó phân theo *số lượng tag*, không theo nghề. 4/8 cụm bị gắn cờ
`low_confidence`.

**Ý nghĩa.** Kỹ năng trong ngành data **chồng lấn liên tục**, không phân thành khối rời rạc. Điều này
giải thích luôn vì sao title ở VN lộn xộn và vì sao cần một engine gán nhãn ngay từ đầu.

### C5. 30 tin mà 3 model mạnh đọc ra 3 nghề khác nhau

**Phát hiện.** `Analyst` · `AI Solutions Architect` · `Platform Engineer` — mỗi model chọn một nhánh
khác nhau và **đều có lý**. Phải dùng một tầng thứ hai (thu hẹp lựa chọn + JD đầy đủ + buộc trích dẫn
bằng chứng, cuối cùng là đấu loại nhị phân) mới chốt được.

**Ý nghĩa.** Đây là **bằng chứng định lượng cho luận điểm mở đầu của dự án**: tiêu đề công việc ở Việt
Nam không đủ để biết đó là nghề gì. Chính vì thế mới cần bước gán nhãn.

---

## Những điều KHÔNG nên viết trong báo cáo

| Đừng | Vì |
|---|---|
| Xếp hạng #1 ở **cấp family** | Thứ tự lật khi đổi judge (C1) |
| Gọi cụm là "nhóm nghề tự nhiên" | Silhouette 0,13–0,20 = không có cấu trúc (C4) |
| Trích topic có `interpretable=False` | Là boilerplate của nhà tuyển dụng, không phải chủ đề |
| Trích cụm/topic theo **số ID** | ID đổi mỗi lần chạy — trích theo dominant family + skill |
| Nói **"accuracy"** | Hiện chỉ có **reliability** (86,8% đồng thuận judge) + **face validity** (30 tin đã đọc và thấy lý do hợp lý). Accuracy cần gán nhãn "mù" |
| Suy luận **xu hướng/tăng trưởng** | Chỉ có 1 snapshot |
| Nói gì về **lương** | Không có trong dữ liệu |
| Coi tỉ lệ ngành là tỉ lệ toàn thị trường | 35,1% chưa phân loại được ngành — phải nói rõ mẫu số |

---

## Mạch báo cáo gợi ý (descriptive → diagnostic → prescriptive)

1. **Vấn đề** — title lộn xộn nên không đọc được thị trường (dẫn bằng C5: 30 tin, 3 model, 3 đáp án).
2. **Descriptive** — A1 (3 nhánh chính) → A5 (lõi kỹ năng) → A4 (ai tuyển) → A3 (cấp bậc).
3. **Diagnostic** — A2 (vì sao BA khó phân loại) · B3 (vì sao HN lệch Governance) · B4 (mảng database ẩn).
4. **Prescriptive** — B1 (lộ trình SQL+Python rồi rẽ nhánh) · B2 (combo bắt buộc) · A3 (nhắm Mid vì
   Junior hiếm; nếu muốn dễ vào thì AI/ML, khó nhất là Data Engineering).
5. **Đánh giá độ tin cậy** — C1..C4, và bảng "không nên viết" ở trên. Phần này là điểm khác biệt.

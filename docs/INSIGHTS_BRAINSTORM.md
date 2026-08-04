# Insight cho báo cáo — nhìn vào là hiểu ngay

*Cập nhật 2026-08-03. Tập phân tích: **720 tin** Data/AI, 6 job board Việt Nam, một lát cắt 16/06/2026.*

> **Nguyên tắc của file này.** Mỗi mục là **một câu có thể đặt lên slide** và người nghe hiểu ngay, không
> cần giải thích phương pháp. Nếu một phát hiện phải giải thích kỹ thuật mới hiểu được thì nó **không
> thuộc về đây** — cho xuống phụ lục.
>
> Nguồn số: `gold_*` trong warehouse · `docs/CAREER_MAP_FINDINGS.md` (tự sinh) ·
> xem nhanh bằng `python analysis/explore.py sql "..."`.

---

# PHẦN 1 — MÔ TẢ: thị trường trông ra sao

## 1.1. Ngành data ở Việt Nam là ngành *phân tích*, không phải ngành *làm mô hình*

**Gần một nửa (46,9%) tin tuyển dụng thuộc nhánh Analytics** — người biến dữ liệu thành quyết định.
Data Engineering 20,1%, AI/ML 24,9%.

Trong khi đó các vai trò làm mô hình thuần rất mỏng: **Data Scientist chỉ 4,3%**, ML Engineer ~1%,
Research Scientist dưới 1%.

> **Câu để nói:** *"Truyền thông nói về AI, nhưng gần một nửa nhu cầu thật là người đọc số và làm báo cáo."*

## 1.2. Bốn nghề lớn nhất **ngang nhau**, không có nghề nào áp đảo

Business Analyst 146 · Data Engineer 125 · AI Engineer 110 · Data Analyst 105 — bốn nghề này cộng lại
chiếm **2/3 thị trường**, và chênh nhau nằm trong sai số.

> **Câu để nói:** *"Không có 'nghề hot nhất'. Có bốn cửa vào rộng gần bằng nhau."*
> ⚠️ Đừng xếp hạng bốn nghề này — chênh lệch nhỏ hơn sai số của phép đo.

## 1.3. Ba kỹ năng đi khắp mọi nghề

**SQL 47,8% · Python 43,5% · Data Analysis 39,6%** — cộng thêm Reporting 38,3%.

Đây là **lõi chung**: học ba thứ này thì mở được cửa ở mọi nhánh. Sự khác biệt giữa các nghề **không nằm
ở lõi** mà ở phần rìa.

## 1.4. Tiếng Anh là kỹ năng thật, không phải điểm cộng

**33,8%** tin yêu cầu tiếng Anh — đứng thứ 5, trên cả Machine Learning.

Và nó **lệch rất mạnh theo ngành**:

| Ngành | % đòi tiếng Anh |
|---|--:|
| Công nghệ / Phần mềm | **48,8%** |
| Logistics | 32,1% |
| Sản xuất | 32,0% |
| Ngân hàng / Tài chính | 25,4% |
| Thương mại điện tử | **16,7%** |

> **Câu để nói:** *"Vào công ty công nghệ thì cứ hai tin là một tin đòi tiếng Anh. Vào e-commerce thì
> cứ sáu tin mới có một."*

## 1.5. Gần như không có việc remote

**Chỉ 35/720 tin (4,9%)** cho làm từ xa.

> **Câu để nói:** *"Nếu bạn muốn làm data từ xa ở Việt Nam, thị trường gần như không có chỗ."*

## 1.6. Hà Nội và TP.HCM tuyển giống hệt nhau

Cơ cấu nhánh nghề ở hai thành phố chênh nhau chỉ vài điểm phần trăm (Analytics 45,5% vs 49,8%).

> **Câu để nói:** *"Chuyển thành phố không đổi được loại công việc bạn làm được — chỉ đổi số lượng tin."*
> Đây là **kết quả âm tính**, và nó vẫn hữu ích: nó bác bỏ một giả định phổ biến.

---

# PHẦN 2 — CHẨN ĐOÁN: vì sao lại như vậy

## 2.1. Cửa vào hẹp — nhưng không phải vì thiếu vị trí Junior

Junior 17,4% + Intern 2,6% = **20%** thị trường. Nghe như một phần năm, không tệ.

Nhưng nhìn **yêu cầu**:

| Cấp bậc | Số kỹ năng trung bình |
|---|--:|
| Junior | **8,2** |
| Mid | **9,8** |

**Tin Junior đòi gần bằng tin Mid** — chênh chưa tới 2 kỹ năng. Và 15% tin Junior/Intern vẫn nhắc
"2–3 năm kinh nghiệm".

> **Câu để nói:** *"Vấn đề không phải ít chỗ cho người mới. Vấn đề là chỗ cho người mới đòi hỏi gần bằng
> chỗ cho người có kinh nghiệm."*

## 2.2. Thang nghề chỉ đi một chiều

Data Engineer đã có sẵn phần lớn kỹ năng của Data Analyst. Chiều ngược lại thì **không** — từ Data Analyst
sang Data Engineer phải học thêm **cả một danh sách dài**.

> **Câu để nói:** *"Đi từ kỹ thuật sang phân tích thì dễ. Đi ngược lại thì phải học lại gần như từ đầu.
> Nên nghề đầu tiên bạn chọn quyết định sau này bạn đi được đâu."*

## 2.3. Business Analyst: dễ vào, khó ra

Ai cũng vào được BA — người làm Data Analyst hay Data Engineer đều đã có phần lớn hồ sơ kỹ năng của BA.
Nhưng chiều ngược lại thì **BA chỉ có khoảng 1/3 hồ sơ của Data Analyst** (con số này **bền**).

Lý do nằm ở đây: **BA chỉ có đúng MỘT kỹ năng xuất hiện ở hơn nửa số tin.** Data Engineer có sáu,
AI Engineer có năm.

> **Câu để nói:** *"Business Analyst không có chuẩn kỹ năng. Đó là lý do ai cũng vào được, và cũng là lý
> do vào rồi thì khó đi tiếp."*
>
> ⚠️ Đây là chuyện **kỹ năng chuyển đổi**, không phải chuyện "BA có phải nghề data không". BA **là** nghề
> data theo định nghĩa của project.

## 2.4. "AI Engineer" không phải nghề toán — là nghề phần mềm

| Kỹ năng của AI Engineer | % tin |
|---|--:|
| LLM | 69,1% |
| API | 56,4% |
| Docker | 33,6% |
| Cloud | 38,2% |
| **SQL** | **25,5%** |

**AI Engineer dùng SQL ít hơn mặt bằng thị trường**, nhưng hơn một nửa cần API và một phần ba cần Docker.

> **Câu để nói:** *"Người ta tưởng AI Engineer là người giỏi toán. Tin tuyển dụng nói đó là kỹ sư phần mềm
> biết đưa mô hình lên chạy thật."*

## 2.5. Python **không** phải thứ làm nên một Data Analyst

Python xuất hiện ở 42,9% tin Data Analyst — nghe nhiều. Nhưng nó cũng xuất hiện ở **43% toàn thị trường**,
nên nó **không phân biệt được gì**.

Thứ thật sự định nghĩa Data Analyst: **Power BI 61,9% · Statistics 41,0% · Tableau 38,1% · Excel 37,1%**.

> **Câu để nói:** *"Lời khuyên phổ biến là 'muốn làm Data Analyst thì học Python'. Dữ liệu nói: Power BI
> và Excel mới là thứ phân biệt bạn."*
> Đây là insight **đi ngược trực giác** — loại có giá trị nhất.

## 2.6. Công nghệ và ngân hàng tuyển ngang nhau, nhưng tuyển hai thứ khác nhau

Công nghệ/Phần mềm 211 tin · Ngân hàng/Tài chính 205 tin — chênh 0,8 điểm, coi như bằng nhau.

Nhưng **cơ cấu khác hẳn**:

| | Công nghệ | Ngân hàng |
|---|--:|--:|
| AI Engineer | **53** | 19 |
| Business Analyst | 43 | 38 |
| Risk / Fraud | ~0 | **29** |
| Data Governance | 4 | **14** |

Ngân hàng gần như độc chiếm hai nhánh: **Risk/Fraud 29/38 tin** và **Data Governance 14/27 tin** — cả hai
sinh ra từ áp lực tuân thủ pháp lý, không phải từ nhu cầu tự nhiên.

> **Câu để nói:** *"Muốn làm AI thì vào công ty công nghệ. Muốn làm quản trị dữ liệu hay rủi ro thì vào
> ngân hàng. Hai nơi tuyển số lượng như nhau nhưng gần như không cạnh tranh nhau."*

---

# PHẦN 3 — ĐỀ XUẤT: nên làm gì

## 3.1. Bộ kỹ năng tối thiểu để ứng tuyển từng nghề

Kỹ năng xuất hiện ở **hơn nửa** số tin của nghề đó — tức gần như bắt buộc:

| Nghề | Cần có |
|---|---|
| **Data Analyst** | Data Analysis · SQL · Reporting · Power BI |
| **BI** | Power BI · Reporting · SQL · Data Analysis |
| **Data Engineer** | SQL · Python · ETL · Data Management · Data Warehouse · Database |
| **AI Engineer** | Python · AI · Machine Learning · LLM · API |
| **Data Scientist** | Data Science · Machine Learning · Python · Statistics · SQL |
| **Business Analyst** | *chỉ có Business Analysis* |

> **Câu để nói:** *"Bốn thứ. Đó là hàng rào tối thiểu để ứng tuyển Data Analyst — không phải mười lăm thứ
> như các khoá học quảng cáo."*

## 3.2. Lộ trình rẻ nhất mà ít ai nói tới

**Data Analyst → Risk / Fraud Analyst: đã đi được ~83% đường.** Con số này **bền** qua mọi cách đo.

Ngược lại, **Data Analyst → Data Engineer** là bức tường dài nhất.

> **Câu để nói:** *"Nếu bạn đang làm Data Analyst và muốn tăng thu nhập bằng cách vào ngân hàng, đường
> ngắn nhất là Risk/Fraud Analyst — bạn đã có sẵn phần lớn thứ họ cần."*

## 3.3. Học theo bó, đừng học lẻ

Ba nhóm kỹ năng đi liền nhau trong tin tuyển dụng:

- **Nhóm báo cáo:** SQL + Power BI/Tableau + Excel + Reporting → vào DA / BI / Risk
- **Nhóm hạ tầng:** SQL + Python + ETL + Data Warehouse + Cloud → vào Data Engineer
- **Nhóm AI ứng dụng:** Python + Machine Learning + LLM + API + Docker → vào AI Engineer

> **Câu để nói:** *"Học nửa bó thì không mở được cửa nào. Ba bó này gần như không giao nhau ngoài SQL và
> Python."*

## 3.4. Cho nhà tuyển dụng

- **Tin Junior của bạn đang đòi gần bằng tin Mid** — nếu thật sự muốn tuyển người mới thì phải cắt bớt
  yêu cầu, không phải chỉ đổi chữ trong tiêu đề.
- **Chức danh "Business Analyst" không truyền đạt được gì** — hai người cùng chức danh này có thể làm hai
  việc khác hẳn. Mô tả công việc cụ thể sẽ lọc ứng viên tốt hơn chức danh.
- **Nếu không đòi tiếng Anh thì nói rõ** — 2/3 thị trường không đòi, đó là lợi thế cạnh tranh khi tuyển.

---

# PHẦN 4 — Ba điều phải nói kèm mọi con số

Đây là phần làm báo cáo đáng tin, và cũng là phần nhiều bài bỏ qua.

**1. Đây là số của 720 tin đã thu thập, không phải của thị trường Việt Nam.**
Mỗi job board được tìm với bộ từ khoá khác nhau, và cơ cấu nghề của chúng khác nhau rất xa — tỉ lệ
Analytics dao động từ 25,5% (Glints) tới 60,4% (VietnamWorks). VietnamWorks đóng góp 255/720 tin, nên
con số tổng nghiêng về nó.

**2. Chỉ có một lát cắt ngày 16/06/2026.**
Không có gì để so sánh ⇒ **mọi câu "đang tăng", "đang hot", "nhu cầu giảm" đều không có cơ sở.**

**3. Không có dữ liệu lương.**
Job board không cho lấy ⇒ **không một câu nào về thu nhập.**

---

# Phụ lục — ba kỹ thuật đã thử, không dùng được

Gói gọn trong ba câu. Dám nói "đã thử, không ra, đây là lý do" vẫn là điểm cộng, nhưng không đáng
dành cho nó một chương.

**Phân cụm kỹ năng (KMeans).** Chạy với k từ 2 đến 20, chỉ số tách cụm (silhouette) chỉ dao động
**0,125–0,174** — theo quy ước là *không có cấu trúc cụm đáng kể*. Nguyên nhân chính là phát hiện ở mục
1.3: các nghề chia sẻ một **lõi kỹ năng chung quá mạnh**, nên mọi tin đều na ná nhau và không tách nhóm được.

**Topic modeling trên mô tả công việc (NMF).** Trong 9 chủ đề tìm được, **6 chủ đề tách theo NGÔN NGỮ của
tin hoặc theo job board**, không theo nội dung nghề — dữ liệu song ngữ Việt–Anh nên mô hình bắt được ngôn
ngữ trước khi bắt được ý nghĩa.

**Luật kết hợp kỹ năng.** Sinh ra hơn 1.200 luật vượt kiểm định thống kê, nhưng các luật mạnh nhất đều
hiển nhiên (SQL đi với Python, báo cáo đi với SQL) và mức vượt trội so với ngẫu nhiên chỉ khoảng 1,2 lần.
**Chính điều đó là phát hiện** — thị trường có lõi chung rất mạnh, khác biệt giữa các nghề nằm ở phần rìa
chứ không ở lõi. Kết luận này đã được đưa lên mục 1.3; phần luật chi tiết không cần trong báo cáo.

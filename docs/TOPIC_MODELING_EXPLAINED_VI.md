# Giải Thích Topic Modeling

Topic modeling ở đây dùng để đọc phần JD/free-text và tìm các chủ đề lặp lại trong tin tuyển dụng Data/AI. Đây là bước khám phá, không phải model dự đoán.

## Cách Hiểu Nhanh

- `topic_id`: mã chủ đề do NMF tìm ra.
- `top_terms`: các từ/cụm từ có trọng số cao nhất, dùng để diễn giải topic.
- `dominant_topic`: topic mạnh nhất của một job.
- `topic_weight`: mức độ job gắn với topic đó.

Model không học từ `job_family`. `job_family` chỉ được dùng sau khi đã gán topic để xem topic nào nghiêng về family nào.

## Kết Quả Chính

Script chọn `9` topic.

| Topic | Số job | % job | Family nổi bật | Top terms |
|---:|---:|---:|---|---|
| 1 | 183 | 25.4 | `BUSINESS_ANALYST` | business; systems; technical; development; performance; across; ensure; design; solutions; communication |
| 2 | 136 | 18.9 | `AI_ENGINEER` | ai; learning; llm; machine; machine learning; python; engineer; ai engineer; vision; pytorch |
| 3 | 95 | 13.2 | `DATA_ENGINEER` | lake; data warehouse; warehouse; data lake; etl; data engineer; elt; spark; lake data; airflow |
| 4 | 69 | 9.6 | `BUSINESS_ANALYST` | business analyst; business; analyst; business analysis; agile; erp; analyst domain; expertise business; office business; agile business |
| 7 | 64 | 8.9 | `DATA_ANALYST` | bi; power bi; power; tableau; data analyst; excel; sql; analyst; dashboard; reporting |
| 0 | 60 | 8.3 | `BUSINESS_ANALYST` | phap; thuat; tang; tao; huong; nhu; lap; cuu; nghien cuu; nghien |
| 5 | 55 | 7.6 | `RISK_FRAUD_ANALYST` | rui; ngan; khoi; chung; tuan; soat; thieu; khoa; data science; risk |
| 8 | 42 | 5.8 | `DATA_ENGINEER` | oracle; sql server; server; sql; mysql; postgresql; sql sql; database; etl; oracle postgresql |
| 6 | 16 | 2.2 | `AI_ENGINEER` | thoai; email; ngay; sinh gioi; chuong; ai trung; lich hen; hen; email truong; truong bat |

Lưu ý: `top_terms` là output trực tiếp từ model nên có thể không dấu, đặc biệt với JD tiếng Việt đã được normalize.

## Nên Dùng Kết Quả Này Thế Nào

Dùng topic modeling để bổ sung cho:

1. Market share theo `job_family`.
2. Association rules giữa các skill.
3. Skill clustering.

Topic nào có nhiều family trộn lẫn thì nên đọc như một chủ đề công việc chung, không đọc như một nhãn nghề mới.

## Hạn Chế

- JD có cả tiếng Việt và tiếng Anh nên term có thể có nhiều biến thể.
- Topic là chủ đề text, không phải nhãn nghề chính thức.
- Dữ liệu chỉ là một snapshot, không suy ra xu hướng tăng/giảm.
- Không có salary, không suy luận về thu nhập.

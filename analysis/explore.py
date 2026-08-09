"""Mở kho dữ liệu để xem — ba cách, chọn cách hợp với việc đang làm.

    python analysis/explore.py ui        # giao diện web: bấm chuột xem bảng như Excel
    python analysis/explore.py list      # liệt kê mọi bảng + số dòng
    python analysis/explore.py show <ten_bang> [n]   # xem n dòng đầu của một bảng
    python analysis/explore.py sql "SELECT ..."      # chạy một câu SQL
    python analysis/explore.py csv       # xuất mọi bảng ra CSV để mở bằng Excel

Mở ở chế độ CHỈ ĐỌC, nên không có cách nào làm hỏng dữ liệu.
"""

from __future__ import annotations

import sys
from pathlib import Path

import duckdb

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.utils.analysis_base import force_utf8_stdout  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "warehouse.duckdb"
# Đích của bản xuất CSV nằm dưới `data/`, tức là vùng đã gitignore. Đây là bản CHỤP để mở bằng Excel,
# không phải kết quả phân tích — commit nó vào repo là tạo ra một bản sao thứ hai của kho dữ liệu và
# bản sao đó sẽ lệch dần. `analysis/outputs/` được git theo dõi nên không dùng làm chỗ này.
CSV_DIR = ROOT / "data" / "csv_export"


def _con():
    if not DB.exists():
        sys.exit(f"khong tim thay {DB}")
    return duckdb.connect(str(DB), read_only=True)


def cmd_ui() -> None:
    """Giao diện web tích hợp của DuckDB: duyệt bảng, chạy SQL, xem kết quả dạng lưới."""
    con = duckdb.connect(str(DB))          # UI cần quyền ghi để lưu notebook của chính nó
    con.execute("INSTALL ui")
    con.execute("LOAD ui")
    con.execute("CALL start_ui()")
    print("Giao dien da mo tai http://localhost:4213")
    print("  - cot trai: danh sach bang, bam vao de xem du lieu")
    print("  - o giua  : go SQL roi Ctrl+Enter de chay")
    print("\nNhan Ctrl+C o day de dong.")
    try:
        import time
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        print("\nda dong.")
    finally:
        con.close()


def cmd_list() -> None:
    con = _con()
    rows = con.execute("SELECT table_name FROM information_schema.tables "
                       "WHERE table_schema='main' ORDER BY 1").fetchall()
    print(f"{'bang':30s} {'so dong':>9s}  {'so cot':>6s}")
    print("-" * 50)
    for (t,) in rows:
        n = con.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
        c = len(con.execute(f'DESCRIBE "{t}"').fetchall())
        print(f"{t:30s} {n:9,d}  {c:6d}")
    con.close()


def cmd_show(name: str, n: int = 20) -> None:
    con = _con()
    print(f"--- cot cua {name} ---")
    for col, typ, *_ in con.execute(f'DESCRIBE "{name}"').fetchall():
        print(f"  {col:24s} {typ}")
    total = con.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]
    print(f"\n--- {n} dong dau (tong {total:,}) ---")
    df = con.execute(f'SELECT * FROM "{name}" LIMIT {int(n)}').df()
    print(df.to_string(max_colwidth=40, max_cols=12))
    con.close()


def cmd_sql(q: str) -> None:
    con = _con()
    df = con.execute(q).df()
    print(df.to_string(max_colwidth=50, max_rows=100))
    print(f"\n({len(df):,} dong)")
    con.close()


def cmd_csv() -> None:
    """Xuất mọi bảng ra CSV. Đây là bản CHỤP để xem bằng Excel — nguồn thật vẫn là warehouse."""
    con = _con()
    CSV_DIR.mkdir(parents=True, exist_ok=True)
    rows = con.execute("SELECT table_name FROM information_schema.tables "
                       "WHERE table_schema='main' ORDER BY 1").fetchall()
    for (t,) in rows:
        out = CSV_DIR / f"{t}.csv"
        # Ghi qua pandas với `utf-8-sig`, KHÔNG dùng `COPY ... TO`. Hai lý do: DuckDB không nhận tuỳ
        # chọn ENCODING khi ghi, và quan trọng hơn — Excel đọc CSV UTF-8 không có BOM thành chữ Việt
        # vỡ hết dấu. `utf-8-sig` thêm BOM nên mở bằng Excel là ra tiếng Việt đúng.
        df = con.execute(f'SELECT * FROM "{t}"').df()
        df.to_csv(out, index=False, encoding="utf-8-sig")
        print(f"  {len(df):7,d} dong -> {out.relative_to(ROOT)}")
    con.close()
    print(f"\nXong. Mo bang Excel tu: {CSV_DIR.relative_to(ROOT)}")
    print("LUU Y: day la ban chup. Sua file CSV KHONG lam doi du lieu that.")


def main() -> None:
    force_utf8_stdout()
    if len(sys.argv) < 2:
        print(__doc__)
        return
    cmd, *rest = sys.argv[1:]
    if cmd == "ui":
        cmd_ui()
    elif cmd == "list":
        cmd_list()
    elif cmd == "show":
        cmd_show(rest[0], int(rest[1]) if len(rest) > 1 else 20)
    elif cmd == "sql":
        cmd_sql(rest[0])
    elif cmd == "csv":
        cmd_csv()
    else:
        print(__doc__)


if __name__ == "__main__":
    main()

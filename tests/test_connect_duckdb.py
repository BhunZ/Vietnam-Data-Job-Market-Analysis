# from psycopg2 import connect
# from pipeline.transform.gold import run_gold
# import duckdb

# from pipeline.utils.config import DATA_DIR

# DB_PATH = DATA_DIR / "warehouse.duckdb"

# cnn = duckdb.connect(str(DB_PATH))

# query = "SELECT count(*) FROM jobs_silver"
# t = cnn.execute(query)
# result = t.fetchone()
# cnn.close()
import duckdb

from pipeline.utils.config import DATA_DIR

DB_PATH = DATA_DIR / "warehouse.duckdb"

with duckdb.connect(str(DB_PATH)) as conn:

    print("===== TABLES =====")

    tables = conn.execute("SHOW TABLES").fetchall()

    for table in tables:
        print(table[0])

    print()

    count = conn.execute(
        """
        SELECT COUNT(*)
        FROM jobs_silver
        """
    ).fetchone()[0]

    print("jobs_silver rows:", count)
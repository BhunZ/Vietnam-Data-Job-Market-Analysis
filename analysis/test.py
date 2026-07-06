import duckdb

con = duckdb.connect("D:/ptdl/Vietnam-Data-Job-Market-Analysis/data/warehouse.duckdb", read_only=True)

con.sql("""
SELECT job_family, n, pct
FROM gold_market_share
ORDER BY n DESC
""").show()

con.sql("""
SELECT job_family, skill, n, share_in_family
FROM gold_family_skill
ORDER BY job_family, n DESC
LIMIT 50
""").show()
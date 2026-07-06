import duckdb
from pipeline.utils.config import DATA_DIR

DB_PATH = DATA_DIR / "warehouse.duckdb"

with duckdb.connect(str(DB_PATH)) as conn:
    # jobs_silver
    jobs = conn.execute("""
        SELECT *
        FROM jobs_silver
        LIMIT 15
    """).fetchdf()

    # skill_demand
    skill = conn.execute("""
        SELECT *
        FROM skill_demand
        LIMIT 15
    """).fetchdf()

    # role_skill_matrix
    role_skill = conn.execute("""
        SELECT *
        FROM role_skill_matrix
        LIMIT 15
    """).fetchdf()

    # role_by_location
    role_location = conn.execute("""
        SELECT *
        FROM role_by_location
        LIMIT 15
    """).fetchdf()

    company_type = conn.execute("""
        SELECT *
        FROM company_type_demand
        LIMIT 15
    """).fetchdf()

    # seniority_progression
    seniority_progression = conn.execute("""
        SELECT *
        FROM seniority_progression
        LIMIT 15
    """).fetchdf()

    # skill_combinations
    skill_combinations = conn.execute("""
        SELECT *
        FROM skill_cooccurrence
        LIMIT 15
    """).fetchdf()


    # trend
    trend = conn.execute("""
        SELECT *
        FROM trend
        LIMIT 15
    """).fetchdf()

    print("===== jobs_silver =====")
    print(jobs)

    print("\n===== skill_demand =====")
    print(skill)

    print("\n===== role_skill_matrix =====")
    print(role_skill)

    print("\n===== seniority_progression =====")
    print(seniority_progression)

    print("\n===== role_by_location =====")
    print(role_location)

    print("\n===== company_type =====")
    print(company_type)

    print("\n===== skill_combinations =====")
    print(skill_combinations)

    print("\n===== trend =====")
    print(trend)


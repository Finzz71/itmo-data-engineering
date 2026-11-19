from getpass import getpass

import duckdb

secret = getpass("Secret Key RustFS: ").replace("'", "''")

with duckdb.connect() as db:
    db.execute("INSTALL httpfs")
    db.execute("LOAD httpfs")
    db.execute(f"""
        CREATE SECRET rustfs (
            TYPE s3,
            KEY_ID 'hhadmin',
            SECRET '{secret}',
            REGION 'us-east-1',
            ENDPOINT 'localhost:9010',
            URL_STYLE 'path',
            USE_SSL false,
            SCOPE 's3://hh-lake/'
        )
    """)

    db.execute(r"""
        CREATE TEMP TABLE php_vacancies AS
        SELECT list_distinct(list_filter(
            list_transform(
                string_split(coalesce(key_skills, ''), ';'),
                lambda skill: lower(regexp_replace(
                    skill,
                    '^[\s\p{Z}\x{0085}\x{000B}\x{001C}-\x{001F}]+|[\s\p{Z}\x{0085}\x{000B}\x{001C}-\x{001F}]+$',
                    '',
                    'g'
                ))
            ),
            lambda skill: skill <> ''
        )) AS skills
        FROM read_csv(
            's3://hh-lake/it_vacancies_2024.csv',
            header = true,
            delim = ',',
            quote = '"',
            escape = '"',
            all_varchar = true
        )
        WHERE regexp_matches(lower(name), '(^|[^a-z0-9_])php([^a-z0-9_]|$)')
    """)

    vacancies = db.execute("SELECT count(*) FROM php_vacancies").fetchone()[0]
    print(f"Вакансий варианта PHP: {vacancies}")

    all_match = True
    for size in (1, 2, 3):
        columns = ", ".join(f"skill_{i}" for i in range(1, size + 1))
        joins = "\n".join(
            f"CROSS JOIN UNNEST(skills) AS s{i}(skill_{i})"
            for i in range(1, size + 1)
        )
        order_rule = " AND ".join(
            f"skill_{i} < skill_{i + 1}" for i in range(1, size)
        ) or "TRUE"

        db.execute(f"""
            CREATE OR REPLACE TEMP TABLE duckdb_counts AS
            SELECT {columns}, count(*) AS count
            FROM php_vacancies
            {joins}
            WHERE {order_rule}
            GROUP BY {columns}
        """)

        db.execute(f"""
            CREATE OR REPLACE TEMP TABLE mapreduce_counts AS
            SELECT {columns}, CAST(count AS BIGINT) AS count
            FROM read_csv(
                's3://hh-lake/results/php/failure_test/mapreduce_skills_{size}.csv',
                header = true,
                delim = ',',
                all_varchar = true
            )
        """)

        total = db.execute("SELECT count(*) FROM duckdb_counts").fetchone()[0]
        differences = db.execute("""
            SELECT count(*) FROM (
                (SELECT * FROM duckdb_counts EXCEPT ALL SELECT * FROM mapreduce_counts)
                UNION ALL
                (SELECT * FROM mapreduce_counts EXCEPT ALL SELECT * FROM duckdb_counts)
            ) AS diff
        """).fetchone()[0]

        print(f"Размер стека {size}. Строк DuckDB: {total}. Различий: {differences}")
        all_match = all_match and differences == 0

    if not all_match:
        raise SystemExit("Таблицы частот различаются")
    print("Все три таблицы частот совпали")

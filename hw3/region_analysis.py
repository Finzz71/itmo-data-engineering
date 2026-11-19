import csv
import io
import re
from collections import Counter
from itertools import combinations, islice

from getpass import getpass
import boto3
from botocore.config import Config

from collections import defaultdict
from itertools import combinations
from pathlib import Path
from statistics import median

bucket = "hh-lake"
key = "it_vacancies_2024.csv"

s3 = boto3.client(
    "s3",
    endpoint_url="http://localhost:9010",
    aws_access_key_id="hhadmin",
    aws_secret_access_key=getpass("Secret Key RustFS: "),
    region_name="us-east-1",
    config=Config(s3={"addressing_style": "path"}),
)

class S3Stream(io.RawIOBase):
    def __init__(self, body):
        self.body = body

    def readable(self):
        return True

    def readinto(self, buffer):
        data = self.body.read(len(buffer))
        buffer[:len(data)] = data
        return len(data)

REGIONS = ("Москва", "Санкт-Петербург", "Новосибирск")
php_title = re.compile(r"(?<![a-z0-9_])php(?![a-z0-9_])")

vacancy_counts = Counter()
salary_values = defaultdict(list)
skill_counts = {region: Counter() for region in REGIONS}

response = s3.get_object(Bucket=bucket, Key=key)

with response["Body"] as body:
    with io.TextIOWrapper(
        io.BufferedReader(S3Stream(body)),
        encoding="utf-8-sig",
        newline="",
    ) as stream:
        for row in csv.DictReader(stream):
            region = (row["area"] or "").strip()
            if region not in REGIONS:
                continue
            if not php_title.search(row["name"].lower()):
                continue

            vacancy_counts[region] += 1
            skills = sorted({
                skill.strip().lower()
                for skill in (row["key_skills"] or "").split(";")
                if skill.strip()
            })

            for size in (1, 2, 3):
                skill_counts[region].update(combinations(skills, size))

            if row["currency"] != "RUR":
                continue
            if (row["gross"] or "").strip().lower() != "false":
                continue

            bounds = [
                float(row[field])
                for field in ("salary_from", "salary_to")
                if (row[field] or "").strip()
            ]
            if not bounds or any(value <= 0 for value in bounds):
                continue
            if len(bounds) == 2 and bounds[0] > bounds[1]:
                continue

            salary_values[region].append(sum(bounds) / len(bounds))

output_dir = Path("results")
output_dir.mkdir(exist_ok=True)

salary_rows = []
skill_rows = []

print("Регион | Все вакансии | С подходящей зарплатой | Медиана, руб.")

for region in REGIONS:
    values = salary_values[region]
    salary_median = median(values) if values else None

    salary_rows.append({
        "region": region,
        "vacancies": vacancy_counts[region],
        "salary_count": len(values),
        "median_rub": salary_median,
    })

    median_text = f"{salary_median:.0f}" if values else "нет данных"
    print(
        f"{region} | {vacancy_counts[region]} | "
        f"{len(values)} | {median_text}"
    )

    for size in (1, 2, 3):
        counts = [
            (stack, count)
            for stack, count in skill_counts[region].items()
            if len(stack) == size
        ]
        counts.sort(key=lambda item: (-item[1], item[0]))

        for stack, count in counts[:5]:
            skill_rows.append({
                "region": region,
                "stack_size": size,
                "skills": " + ".join(stack),
                "count": count,
                "share_percent": count / vacancy_counts[region] * 100,
            })

print("\nРегион | Размер стека | Навыки | Вакансий | Доля, %")
for row in skill_rows:
    print(
        f"{row['region']} | {row['stack_size']} | "
        f"{row['skills']} | {row['count']} | "
        f"{row['share_percent']:.1f}%"
    )

for filename, rows in (
    ("region_salaries.csv", salary_rows),
    ("region_skills.csv", skill_rows),
):
    path = output_dir / filename
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f"\nСохранено: {path}")
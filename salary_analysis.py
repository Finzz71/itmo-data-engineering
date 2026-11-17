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

MIN_COUNT = 30
php_title = re.compile(r"(?<![a-z0-9_])php(?![a-z0-9_])")

frequencies = Counter()
salaries = defaultdict(list)
eligible = 0

response = s3.get_object(Bucket=bucket, Key=key)

with response["Body"] as body:
    with io.TextIOWrapper(
        io.BufferedReader(S3Stream(body)),
        encoding="utf-8-sig",
        newline="",
    ) as stream:
        for row in csv.DictReader(stream):
            if not php_title.search(row["name"].lower()):
                continue

            skills = sorted({
                skill.strip().lower()
                for skill in (row["key_skills"] or "").split(";")
                if skill.strip()
            })

            stacks = [
                stack
                for size in (1, 2, 3)
                for stack in combinations(skills, size)
            ]
            frequencies.update(stacks)

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

            salary = sum(bounds) / len(bounds)
            eligible += 1
            for stack in stacks:
                salaries[stack].append(salary)

print(f"Вакансий с подходящей зарплатой: {eligible}")
print(f"Минимум зарплатных наблюдений: {MIN_COUNT}")

output_dir = Path("results")
output_dir.mkdir(exist_ok=True)

for size in (2, 3):
    results = []

    for stack, values in salaries.items():
        if len(stack) != size or len(values) < MIN_COUNT:
            continue

        # Базу выбираем по частоте во всей выборке PHP-вакансий.
        candidates = list(combinations(stack, size - 1))
        baseline = min(
            candidates,
            key=lambda item: (-frequencies[item], item),
        )
        baseline_values = salaries[baseline]

        stack_median = median(values)
        baseline_median = median(baseline_values)
        difference = stack_median - baseline_median

        results.append({
            "skills": " + ".join(stack),
            "salary_count": len(values),
            "median_rub": stack_median,
            "baseline": " + ".join(baseline),
            "baseline_salary_count": len(baseline_values),
            "baseline_median_rub": baseline_median,
            "difference_rub": difference,
            "difference_percent": difference / baseline_median * 100,
        })

    results.sort(key=lambda item: (-item["difference_rub"], item["skills"]))

    if not results:
        print(f"\nРазмер стека {size}: подходящих сочетаний нет")
        continue

    output_path = output_dir / f"salary_skills_{size}.csv"
    with output_path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(results[0]))
        writer.writeheader()
        writer.writerows(results)

    positive = [row for row in results if row["difference_rub"] > 0][:5]
    negative = sorted(
        (row for row in results if row["difference_rub"] < 0),
        key=lambda item: (item["difference_rub"], item["skills"]),
    )[:5]

    for title, rows in (("Повышение медианы", positive), ("Снижение медианы", negative)):
        print(f"\nРазмер стека {size}. {title}")
        for row in rows:
            print(
                f"{row['skills']} | n = {row['salary_count']} | "
                f"медиана = {row['median_rub']:.0f} | "
                f"база = {row['baseline']} | "
                f"медиана базы = {row['baseline_median_rub']:.0f} | "
                f"разница = {row['difference_rub']:+.0f} руб. "
                f"({row['difference_percent']:+.1f}%)"
            )

    print(f"Сохранено: {output_path}")

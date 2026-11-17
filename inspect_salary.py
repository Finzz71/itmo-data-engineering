import csv
import io
import re
from collections import Counter
from itertools import combinations, islice

from getpass import getpass
import boto3
from botocore.config import Config

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

php_title = re.compile(r"(?<![a-z0-9_])php(?![a-z0-9_])")

currencies = Counter()
salary_fields = Counter()
gross_values = Counter()
regions = Counter()
examples = []
total = 0

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

            total += 1
            salary_from = (row["salary_from"] or "").strip()
            salary_to = (row["salary_to"] or "").strip()

            currencies[(row["currency"] or "").strip() or "не указана"] += 1
            gross_values[(row["gross"] or "").strip() or "не указан"] += 1
            regions[(row["area"] or "").strip() or "не указан"] += 1

            if salary_from and salary_to:
                salary_fields["обе границы"] += 1
            elif salary_from:
                salary_fields["только нижняя граница"] += 1
            elif salary_to:
                salary_fields["только верхняя граница"] += 1
            else:
                salary_fields["зарплата отсутствует"] += 1

            if (salary_from or salary_to) and len(examples) < 5:
                examples.append((
                    row["name"],
                    salary_from,
                    salary_to,
                    row["currency"],
                    row["gross"],
                ))

print(f"PHP-вакансий: {total}")

for title, counts in (
    ("Валюты", currencies),
    ("Заполнение зарплаты", salary_fields),
    ("Значения gross", gross_values),
    ("Топ-10 регионов", Counter(dict(regions.most_common(10)))),
):
    print(f"\n{title}")
    for value, count in counts.most_common():
        print(f"{value}: {count}")

print("\nПримеры: название | от | до | валюта | gross")
for example in examples:
    print(" | ".join(str(value) for value in example))
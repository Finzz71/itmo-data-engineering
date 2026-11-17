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

PHP_TITLE = re.compile(r"(?<![a-z0-9_])php(?![a-z0-9_])")
CHUNK_ROWS = 5_000

class S3Stream(io.RawIOBase):
    def __init__(self, body):
        self.body = body

    def readable(self):
        return True

    def readinto(self, buffer):
        data = self.body.read(len(buffer))
        buffer[:len(data)] = data
        return len(data)

def map_chunk(rows):
    counts = Counter()
    matched = 0
    for row in rows:
        if not PHP_TITLE.search(row["name"].lower()):
            continue
        matched += 1
        skills = sorted({
            skill.strip().lower()
            for skill in (row["key_skills"] or "").split(";")
            if skill.strip()
        })
        for size in (1, 2, 3):
            counts.update(combinations(skills, size))
    return matched, counts

totals = Counter()
matched_total = 0
scanned_total = 0
response = s3.get_object(Bucket=bucket, Key=key)

with response["Body"] as body:
    with io.TextIOWrapper(
        io.BufferedReader(S3Stream(body)), encoding="utf-8-sig", newline=""
    ) as stream:
        rows = csv.DictReader(stream)
        while chunk := list(islice(rows, CHUNK_ROWS)):
            matched, partial_counts = map_chunk(chunk)
            scanned_total += len(chunk)
            matched_total += matched
            totals.update(partial_counts)

print(f"Прочитано записей: {scanned_total}")
print(f"Вакансий варианта PHP: {matched_total}")

for size in (1, 2, 3):
    counts = [
        (skills, count)
        for skills, count in totals.items()
        if len(skills) == size
    ]
    counts.sort(key=lambda item: (-item[1], item[0]))

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([f"skill_{i}" for i in range(1, size + 1)] + ["count"])

    for skills, count in counts:
        writer.writerow([*skills, count])

    result_key = f"results/php/mapreduce_skills_{size}.csv"
    s3.put_object(
        Bucket=bucket,
        Key=result_key,
        Body=output.getvalue().encode("utf-8"),
        ContentType="text/csv; charset=utf-8",
    )

    print(f"\nРазмер стека {size}. Уникальных сочетаний: {len(counts)}")
    for skills, count in counts[:5]:
        print(f"{' + '.join(skills)} — {count}")
    print(f"Сохранено: s3://{bucket}/{result_key}")

import csv
import io
import re
from collections import Counter
from itertools import combinations, islice

from getpass import getpass
import boto3
from botocore.config import Config

import atexit
import time

import psutil

def print_metrics(started):
    elapsed = time.perf_counter() - started
    peak_memory = psutil.Process().memory_info().peak_wset / 1024**2
    print(f"Время: {elapsed:.3f} с")
    print(f"Пик памяти процесса: {peak_memory:.1f} MiB")

bucket = "hh-lake"
key = "it_vacancies_2024.csv"

secret = getpass("Secret Key RustFS: ")

started = time.perf_counter()
atexit.register(print_metrics, started)

s3 = boto3.client(
    "s3",
    endpoint_url="http://localhost:9010",
    aws_access_key_id="hhadmin",
    aws_secret_access_key=secret,
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

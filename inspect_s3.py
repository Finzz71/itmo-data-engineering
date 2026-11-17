import csv
from getpass import getpass
from itertools import islice

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

metadata = s3.head_object(Bucket=bucket, Key=key)
print(f"s3://{bucket}/{key}")
print(f"Размер: {metadata['ContentLength'] / 1024**2:.1f} MiB")

response = s3.get_object(Bucket=bucket, Key=key, Range="bytes=0-262143")
with response["Body"] as body:
    sample = body.read().decode("utf-8-sig", errors="replace")

rows = csv.DictReader(sample.splitlines(keepends=True))
print("Столбцы:", ", ".join(rows.fieldnames or []))
for row in islice(rows, 5):
    print(row["name"], "|", repr(row["key_skills"]))
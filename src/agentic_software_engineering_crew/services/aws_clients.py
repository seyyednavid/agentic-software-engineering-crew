import os

import boto3


AWS_REGION = os.getenv("AWS_REGION", "eu-west-2")

sqs_client = boto3.client("sqs", region_name=AWS_REGION)
dynamodb_resource = boto3.resource("dynamodb", region_name=AWS_REGION)
s3_client = boto3.client("s3", region_name=AWS_REGION)
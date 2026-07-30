import json
import os

from .aws_clients import sqs_client


QUEUE_URL = os.environ["SQS_QUEUE_URL"]


def enqueue_job(job_id: str, requirement: str) -> None:
    message = {
        "job_id": job_id,
        "requirement": requirement,
    }

    sqs_client.send_message(
        QueueUrl=QUEUE_URL,
        MessageBody=json.dumps(message),
    )
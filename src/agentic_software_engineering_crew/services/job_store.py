import os
from datetime import datetime, timezone
from typing import Any

from .aws_clients import dynamodb_resource


TABLE_NAME = os.environ["DYNAMODB_TABLE_NAME"]
table = dynamodb_resource.Table(TABLE_NAME)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_job(job_id: str, requirement: str) -> dict[str, Any]:
    timestamp = utc_now_iso()

    item = {
        "job_id": job_id,
        "status": "QUEUED",
        "progress": "Waiting for a worker",
        "current_stage": None,
        "requirement": requirement,
        "created_at": timestamp,
        "updated_at": timestamp,
    }

    table.put_item(
        Item=item,
        ConditionExpression="attribute_not_exists(job_id)",
    )

    return item


def get_job(job_id: str) -> dict[str, Any] | None:
    response = table.get_item(
        Key={"job_id": job_id},
        ConsistentRead=True,
    )
    return response.get("Item")


def update_job(job_id: str, **updates: Any) -> None:
    if not updates:
        return

    updates["updated_at"] = utc_now_iso()

    expression_names: dict[str, str] = {}
    expression_values: dict[str, Any] = {}
    assignments: list[str] = []

    for index, (field, value) in enumerate(updates.items()):
        name_key = f"#field{index}"
        value_key = f":value{index}"

        expression_names[name_key] = field
        expression_values[value_key] = value
        assignments.append(f"{name_key} = {value_key}")

    table.update_item(
        Key={"job_id": job_id},
        UpdateExpression="SET " + ", ".join(assignments),
        ExpressionAttributeNames=expression_names,
        ExpressionAttributeValues=expression_values,
    )
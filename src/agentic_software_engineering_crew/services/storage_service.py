import os
from pathlib import Path

from .aws_clients import s3_client


BUCKET_NAME = os.environ["S3_OUTPUT_BUCKET"]


def upload_zip(
    *,
    zip_path: Path,
    object_key: str,
    download_filename: str,
) -> str:
    s3_client.upload_file(
        str(zip_path),
        BUCKET_NAME,
        object_key,
        ExtraArgs={
            "ContentType": "application/zip",
            "ContentDisposition": (
                f'attachment; filename="{download_filename}"'
            ),
        },
    )
    return object_key


def upload_generated_zip(job_id: str, zip_path: Path) -> str:
    return upload_zip(
        zip_path=zip_path,
        object_key=f"jobs/{job_id}/generated_app.zip",
        download_filename=f"generated-app-{job_id}.zip",
    )


def upload_reports_zip(job_id: str, zip_path: Path) -> str:
    return upload_zip(
        zip_path=zip_path,
        object_key=f"jobs/{job_id}/generation_reports.zip",
        download_filename=f"generation-reports-{job_id}.zip",
    )


def create_download_url(object_key: str, expires_in: int = 900) -> str:
    return s3_client.generate_presigned_url(
        ClientMethod="get_object",
        Params={
            "Bucket": BUCKET_NAME,
            "Key": object_key,
        },
        ExpiresIn=expires_in,
    )
"""
Amazon SQS worker for the Agentic Software Engineering Crew.

The worker:

1. Long-polls Amazon SQS for generation jobs.
2. Reads job metadata from DynamoDB.
3. Creates an isolated output directory for each job.
4. Runs the CrewAI software-generation workflow.
5. Creates a ZIP archive of the generated application.
6. Uploads the ZIP archive to Amazon S3.
7. Updates the job status in DynamoDB.
8. Deletes the SQS message only after successful completion.

Failed jobs are retried automatically by Amazon SQS. After the configured
maximum receive count is reached, the message is moved to the dead-letter
queue.
"""

import json
import logging
import os
import shutil
import signal
import stat
import time
from pathlib import Path
from typing import Any
from zipfile import ZIP_DEFLATED, ZipFile

from agentic_software_engineering_crew.services.aws_clients import (
    sqs_client,
)
from agentic_software_engineering_crew.services.job_store import (
    get_job,
    update_job,
)
from agentic_software_engineering_crew.services.queue_service import (
    QUEUE_URL,
)
from agentic_software_engineering_crew.services.storage_service import (
    upload_generated_zip,
    upload_reports_zip,
)


# ---------------------------------------------------------------------------
# Logging configuration
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=os.getenv(
        "LOG_LEVEL",
        "INFO",
    ).upper(),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Worker configuration
# ---------------------------------------------------------------------------

BASE_OUTPUT_DIR = Path(
    os.getenv(
        "OUTPUT_DIR",
        "/app/outputs",
    )
).resolve()

POLL_WAIT_SECONDS = int(
    os.getenv(
        "SQS_WAIT_TIME_SECONDS",
        "20",
    )
)

VISIBILITY_TIMEOUT_SECONDS = int(
    os.getenv(
        "SQS_VISIBILITY_TIMEOUT_SECONDS",
        "2700",
    )
)

MAX_RECEIVE_COUNT = int(
    os.getenv(
        "SQS_MAX_RECEIVE_COUNT",
        "3",
    )
)

FINAL_RESULT_MAX_LENGTH = int(
    os.getenv(
        "FINAL_RESULT_MAX_LENGTH",
        "10000",
    )
)

POLL_ERROR_DELAY_SECONDS = int(
    os.getenv(
        "POLL_ERROR_DELAY_SECONDS",
        "5",
    )
)

running = True


# ---------------------------------------------------------------------------
# Shutdown handling
# ---------------------------------------------------------------------------

def stop_worker(
    signum: int,
    frame: Any,
) -> None:
    """
    Request a graceful worker shutdown.

    The current message is allowed to finish before the polling loop exits.
    """
    del frame

    global running
    running = False

    logger.info(
        "Worker shutdown requested. signal=%s",
        signum,
    )


signal.signal(
    signal.SIGTERM,
    stop_worker,
)

signal.signal(
    signal.SIGINT,
    stop_worker,
)


# ---------------------------------------------------------------------------
# File-system utilities
# ---------------------------------------------------------------------------

def handle_remove_readonly(
    remove_function,
    path: str,
    exception_info,
) -> None:
    """
    Retry deletion after making a read-only file writable.
    """
    del exception_info

    try:
        os.chmod(
            path,
            stat.S_IWRITE,
        )
        remove_function(path)

    except OSError:
        logger.exception(
            "Unable to remove read-only path: %s",
            path,
        )
        raise


def prepare_job_workspace(
    job_id: str,
) -> tuple[Path, Path, Path, Path, Path]:
    """
    Create a clean, isolated workspace for one generation job.

    Returns:
        A tuple containing:

        - Job output directory
        - Generated application directory
        - Generated ZIP path
    """
    job_output_dir = (
        BASE_OUTPUT_DIR
        / "jobs"
        / job_id
    )

    generated_app_dir = (
        job_output_dir
        / "generated_app"
    )

    reports_dir = (
        job_output_dir
        / "reports"
    )

    zip_path = (
        job_output_dir
        / "generated_app.zip"
    )

    reports_zip_path = (
        job_output_dir
        / "generation_reports.zip"
    )

    if job_output_dir.exists():
        logger.warning(
            "Removing existing job workspace. job_id=%s path=%s",
            job_id,
            job_output_dir,
        )

        shutil.rmtree(
            job_output_dir,
            onerror=handle_remove_readonly,
        )

    generated_app_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    reports_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    logger.info(
        "Job workspace prepared. job_id=%s path=%s",
        job_id,
        job_output_dir,
    )

    return (
        job_output_dir,
        generated_app_dir,
        reports_dir,
        zip_path,
        reports_zip_path,
    )


def create_zip(
    source_dir: Path,
    zip_path: Path,
    empty_directory_message: str,
) -> Path:
    """
    Create a ZIP archive from the generated application directory.

    Raises:
        RuntimeError:
            When the generated application directory contains no files.
    """
    generated_files = [
        file_path
        for file_path in source_dir.rglob("*")
        if file_path.is_file()
    ]

    if not generated_files:
        raise RuntimeError(
            empty_directory_message
        )

    zip_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    if zip_path.exists():
        zip_path.unlink()

    with ZipFile(
        zip_path,
        mode="w",
        compression=ZIP_DEFLATED,
    ) as archive:
        for file_path in generated_files:
            archive.write(
                filename=file_path,
                arcname=file_path.relative_to(
                    source_dir
                ),
            )

    logger.info(
        "Generated ZIP archive created. path=%s file_count=%s",
        zip_path,
        len(generated_files),
    )

    return zip_path


# ---------------------------------------------------------------------------
# SQS message utilities
# ---------------------------------------------------------------------------

def get_receive_count(
    message: dict[str, Any],
) -> int:
    """
    Return the approximate number of times SQS delivered the message.
    """
    raw_receive_count = (
        message
        .get("Attributes", {})
        .get("ApproximateReceiveCount", "1")
    )

    try:
        return max(
            1,
            int(raw_receive_count),
        )

    except (TypeError, ValueError):
        logger.warning(
            "Invalid ApproximateReceiveCount value: %r",
            raw_receive_count,
        )
        return 1


def parse_message_body(
    message: dict[str, Any],
) -> tuple[str, str]:
    """
    Validate and parse an SQS generation-job message.

    Returns:
        A tuple containing the job ID and software requirement.
    """
    raw_body = message.get("Body")

    if not isinstance(raw_body, str):
        raise ValueError(
            "The SQS message does not contain a valid Body."
        )

    try:
        body = json.loads(raw_body)

    except json.JSONDecodeError as error:
        raise ValueError(
            "The SQS message body is not valid JSON."
        ) from error

    if not isinstance(body, dict):
        raise ValueError(
            "The SQS message body must be a JSON object."
        )

    job_id = body.get("job_id")
    requirement = body.get("requirement")

    if not isinstance(job_id, str) or not job_id.strip():
        raise ValueError(
            "The SQS message does not contain a valid job_id."
        )

    if (
        not isinstance(requirement, str)
        or not requirement.strip()
    ):
        raise ValueError(
            "The SQS message does not contain a valid requirement."
        )

    return (
        job_id.strip(),
        requirement.strip(),
    )


def delete_message(
    receipt_handle: str,
) -> None:
    """
    Delete a successfully processed message from the main queue.
    """
    sqs_client.delete_message(
        QueueUrl=QUEUE_URL,
        ReceiptHandle=receipt_handle,
    )


# ---------------------------------------------------------------------------
# Job execution
# ---------------------------------------------------------------------------

def run_crew_workflow(
    job_id: str,
    requirement: str,
    job_output_dir: Path,
):
    """
    Run the CrewAI workflow for one job.

    The environment variable is configured before importing the Crew class.
    This reduces the risk of output paths being captured too early by
    modules that read OUTPUT_DIR during import.
    """
    os.environ["OUTPUT_DIR"] = str(
        job_output_dir
    )
    os.environ["CURRENT_JOB_ID"] = job_id

    # Import after OUTPUT_DIR is set.
    #
    # Tools should still read OUTPUT_DIR when they execute rather than
    # permanently capturing it at module-import time.
    from agentic_software_engineering_crew.crew import (
        AgenticSoftwareEngineeringCrew,
    )

    return (
        AgenticSoftwareEngineeringCrew()
        .crew()
        .kickoff(
            inputs={
                "job_id": job_id,
                "software_requirement": requirement,
                "output_dir": str(job_output_dir),
            }
        )
    )


def process_job(
    message: dict[str, Any],
) -> None:
    """
    Process one SQS generation job.
    """
    receipt_handle = message.get(
        "ReceiptHandle"
    )

    if not isinstance(receipt_handle, str):
        raise ValueError(
            "The SQS message has no valid ReceiptHandle."
        )

    receive_count = get_receive_count(
        message
    )

    job_id: str | None = None
    previous_output_dir = os.environ.get(
        "OUTPUT_DIR"
    )
    previous_job_id = os.environ.get(
        "CURRENT_JOB_ID"
    )

    try:
        job_id, requirement = parse_message_body(
            message
        )

        logger.info(
            "Worker received job. "
            "job_id=%s receive_count=%s requirement_length=%s",
            job_id,
            receive_count,
            len(requirement),
        )

        existing_job = get_job(
            job_id
        )

        if existing_job is None:
            raise RuntimeError(
                f"Job does not exist in DynamoDB: {job_id}"
            )

        existing_status = existing_job.get(
            "status"
        )

        if existing_status == "COMPLETED":
            logger.warning(
                "Duplicate message received for an already completed job. "
                "Deleting message. job_id=%s",
                job_id,
            )

            delete_message(
                receipt_handle
            )
            return

        update_job(
            job_id,
            status="RUNNING",
            progress="Analysing software requirements",
            current_stage="requirements",
            attempt_count=receive_count,
            error_message=None,
        )

        (
            job_output_dir,
            generated_app_dir,
            reports_dir,
            zip_path,
            reports_zip_path,
        ) = prepare_job_workspace(
            job_id
        )

        result = run_crew_workflow(
            job_id=job_id,
            requirement=requirement,
            job_output_dir=job_output_dir,
        )

        update_job(
            job_id,
            current_stage=None,
            progress=(
                "Creating application and report ZIP archives"
            ),
        )

        create_zip(
            source_dir=generated_app_dir,
            zip_path=zip_path,
            empty_directory_message=(
                "The generated application directory is empty."
            ),
        )

        create_zip(
            source_dir=reports_dir,
            zip_path=reports_zip_path,
            empty_directory_message=(
                "The generation reports directory is empty."
            ),
        )

        update_job(
            job_id,
            current_stage=None,
            progress=(
                "Uploading application and reports to Amazon S3"
            ),
        )

        s3_key = upload_generated_zip(
            job_id=job_id,
            zip_path=zip_path,
        )

        reports_s3_key = upload_reports_zip(
            job_id=job_id,
            zip_path=reports_zip_path,
        )

        final_result = (
            result.raw
            if hasattr(result, "raw")
            else str(result)
        )

        final_result_summary = str(
            final_result
        )[:FINAL_RESULT_MAX_LENGTH]

        update_job(
            job_id,
            status="COMPLETED",
            progress="Generation completed successfully",
            current_stage=None,
            s3_key=s3_key,
            reports_s3_key=reports_s3_key,
            final_result=final_result_summary,
            attempt_count=receive_count,
            error_message=None,
        )

        delete_message(
            receipt_handle
        )

        logger.info(
            "Job completed successfully and SQS message deleted. "
            "job_id=%s s3_key=%s reports_s3_key=%s",
            job_id,
            s3_key,
            reports_s3_key,
        )

    except Exception as error:
        logger.exception(
            "Generation job processing failed. "
            "job_id=%s receive_count=%s",
            job_id,
            receive_count,
        )

        if job_id is not None:
            error_message = str(
                error
            )[:1000]

            try:
                if receive_count >= MAX_RECEIVE_COUNT:
                    update_job(
                        job_id,
                        status="FAILED",
                        progress=(
                            "Generation failed after all retry attempts"
                        ),
                        current_stage=None,
                        attempt_count=receive_count,
                        error_message=error_message,
                    )

                    logger.error(
                        "Job reached the maximum retry count. "
                        "The message will be moved to the DLQ. "
                        "job_id=%s receive_count=%s",
                        job_id,
                        receive_count,
                    )

                else:
                    update_job(
                        job_id,
                        status="RETRYING",
                        progress=(
                            f"Generation attempt {receive_count} failed. "
                            "Waiting for an automatic retry."
                        ),
                        current_stage=None,
                        attempt_count=receive_count,
                        error_message=error_message,
                    )

                    logger.warning(
                        "Job will be retried after the SQS visibility "
                        "timeout. job_id=%s next_attempt=%s",
                        job_id,
                        receive_count + 1,
                    )

            except Exception:
                logger.exception(
                    "Unable to update the failed job status in DynamoDB. "
                    "job_id=%s",
                    job_id,
                )

        # Do not delete the SQS message.
        #
        # It will become visible after the visibility timeout. After the
        # configured maxReceiveCount, SQS moves it to the DLQ.
        raise

    finally:
        if previous_output_dir is None:
            os.environ.pop(
                "OUTPUT_DIR",
                None,
            )
        else:
            os.environ["OUTPUT_DIR"] = (
                previous_output_dir
            )

        if previous_job_id is None:
            os.environ.pop(
                "CURRENT_JOB_ID",
                None,
            )
        else:
            os.environ["CURRENT_JOB_ID"] = (
                previous_job_id
            )


# ---------------------------------------------------------------------------
# Queue polling
# ---------------------------------------------------------------------------

def poll_queue() -> None:
    """
    Continuously long-poll the main SQS queue for generation jobs.
    """
    logger.info(
        "Worker started. "
        "queue_url=%s wait_time=%s visibility_timeout=%s "
        "max_receive_count=%s output_dir=%s",
        QUEUE_URL,
        POLL_WAIT_SECONDS,
        VISIBILITY_TIMEOUT_SECONDS,
        MAX_RECEIVE_COUNT,
        BASE_OUTPUT_DIR,
    )

    while running:
        try:
            response = sqs_client.receive_message(
                QueueUrl=QUEUE_URL,
                MaxNumberOfMessages=1,
                WaitTimeSeconds=POLL_WAIT_SECONDS,
                VisibilityTimeout=VISIBILITY_TIMEOUT_SECONDS,
                AttributeNames=[
                    "ApproximateReceiveCount",
                ],
            )

            messages = response.get(
                "Messages",
                [],
            )

            if not messages:
                continue

            for message in messages:
                try:
                    process_job(
                        message
                    )

                except Exception:
                    logger.exception(
                        "SQS message processing did not complete."
                    )

        except Exception:
            logger.exception(
                "Unable to poll the SQS queue."
            )

            if running:
                time.sleep(
                    POLL_ERROR_DELAY_SECONDS
                )

    logger.info(
        "Worker stopped."
    )


# ---------------------------------------------------------------------------
# Application entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    poll_queue()
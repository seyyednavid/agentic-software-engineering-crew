"""
Web interface for the Agentic Software Engineering Crew.

This module provides:

- A browser interface for submitting software requirements.
- A health endpoint for Docker, Amazon ECS, and ALB health checks.
- Asynchronous job creation using Amazon SQS.
- Job-status storage using Amazon DynamoDB.
- Browser and JSON endpoints for monitoring job progress.
- Temporary download links for generated ZIP files stored in Amazon S3.

Architecture:

Browser
    -> Flask web service
    -> DynamoDB job record
    -> Amazon SQS
    -> ECS worker
    -> CrewAI workflow
    -> Amazon S3
    -> DynamoDB completion status
"""

import logging
import os
import uuid
from pathlib import Path

from flask import (
    Flask,
    abort,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)

from agentic_software_engineering_crew.services.job_store import (
    create_job,
    get_job,
    update_job,
)
from agentic_software_engineering_crew.services.queue_service import (
    enqueue_job,
)
from agentic_software_engineering_crew.services.storage_service import (
    create_download_url,
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
# Application paths and configuration
# ---------------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent

MAX_REQUIREMENT_LENGTH = int(
    os.getenv(
        "MAX_REQUIREMENT_LENGTH",
        "10000",
    )
)

MAX_REQUEST_SIZE_BYTES = int(
    os.getenv(
        "MAX_REQUEST_SIZE_BYTES",
        str(64 * 1024),
    )
)

DOWNLOAD_URL_EXPIRY_SECONDS = int(
    os.getenv(
        "DOWNLOAD_URL_EXPIRY_SECONDS",
        "900",
    )
)


# ---------------------------------------------------------------------------
# Flask application
# ---------------------------------------------------------------------------

app = Flask(
    __name__,
    template_folder=str(BASE_DIR / "templates"),
)

# Reject unexpectedly large HTTP requests.
app.config["MAX_CONTENT_LENGTH"] = MAX_REQUEST_SIZE_BYTES


# ---------------------------------------------------------------------------
# Default software requirement
# ---------------------------------------------------------------------------

DEFAULT_REQUIREMENT = """
Build a Flask web application for queue counter management.

The system should allow staff to:
- Create service counters.
- Mark counters as free or busy.
- Assign a customer to the oldest available free counter.
- View all counter statuses from a browser dashboard.
- Reset all counters when needed.

Use in-memory storage for the first version.
The backend should provide JSON API endpoints.
The frontend should allow staff to test the main features from the browser.
""".strip()


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def normalise_requirement(raw_requirement: str | None) -> str:
    """
    Return a cleaned software requirement.

    When the submitted value is empty, the default requirement is used.
    """
    requirement = (raw_requirement or "").strip()

    if not requirement:
        return DEFAULT_REQUIREMENT

    return requirement


def render_submission_error(
    message: str,
    status_code: int,
    job_id: str | None = None,
):
    """
    Render a safe browser response for submission-related failures.
    """
    return render_template(
        "generator_result.html",
        final_result=message,
        zip_available=False,
        generation_success=False,
        run_id=job_id,
    ), status_code


def redirect_to_job_download(
    *,
    job_id: str,
    s3_key_field: str,
    missing_file_message: str,
):
    job = get_job(job_id)

    if job is None:
        abort(
            404,
            description="The requested generation job was not found.",
        )

    status = job.get("status", "UNKNOWN")

    if status != "COMPLETED":
        abort(
            409,
            description=(
                "The requested download is not available because "
                f"the job status is {status}."
            ),
        )

    object_key = job.get(s3_key_field)

    if not object_key:
        abort(
            404,
            description=missing_file_message,
        )

    try:
        download_url = create_download_url(
            object_key=object_key,
            expires_in=DOWNLOAD_URL_EXPIRY_SECONDS,
        )
    except Exception:
        logger.exception(
            "Unable to create S3 download URL. "
            "job_id=%s field=%s object_key=%s",
            job_id,
            s3_key_field,
            object_key,
        )
        abort(
            500,
            description=(
                "The download link could not be created. "
                "Please try again shortly."
            ),
        )

    return redirect(download_url)


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/health")
def health():
    """
    Return a lightweight health response.

    Docker, Amazon ECS, and the Application Load Balancer can use this
    endpoint to verify that the web process is running.

    This endpoint intentionally does not:

    - Call an LLM.
    - Execute CrewAI.
    - Poll Amazon SQS.
    - Query DynamoDB.
    - Access Amazon S3.
    """
    return {
        "status": "healthy",
        "service": "agentic-software-engineering-crew-web",
    }, 200


# ---------------------------------------------------------------------------
# Browser routes
# ---------------------------------------------------------------------------

@app.get("/")
def index():
    """
    Display the software requirement form.
    """
    return render_template(
        "generator_index.html",
        default_requirement=DEFAULT_REQUIREMENT,
    )


@app.post("/generate")
def generate():
    """
    Create an asynchronous software-generation job.

    The request returns quickly after:

    1. Validating the software requirement.
    2. Creating a unique job ID.
    3. Saving the job in DynamoDB.
    4. Sending the job to Amazon SQS.
    5. Redirecting the browser to the job status page.

    CrewAI is not executed inside this HTTP request.
    """
    software_requirement = normalise_requirement(
        request.form.get("software_requirement")
    )

    if len(software_requirement) > MAX_REQUIREMENT_LENGTH:
        return render_submission_error(
            message=(
                "The software requirement is too long. "
                f"The maximum permitted length is "
                f"{MAX_REQUIREMENT_LENGTH:,} characters."
            ),
            status_code=400,
        )

    job_id = uuid.uuid4().hex

    logger.info(
        "Creating generation job. "
        "job_id=%s requirement_length=%s",
        job_id,
        len(software_requirement),
    )

    try:
        create_job(
            job_id=job_id,
            requirement=software_requirement,
        )

        logger.info(
            "Job record created in DynamoDB. job_id=%s",
            job_id,
        )

        enqueue_job(
            job_id=job_id,
            requirement=software_requirement,
        )

        logger.info(
            "Generation job sent to SQS. job_id=%s",
            job_id,
        )

        return redirect(
            url_for(
                "job_status_page",
                job_id=job_id,
            )
        )

    except Exception:
        logger.exception(
            "Unable to submit generation job. job_id=%s",
            job_id,
        )

        # create_job may have succeeded before enqueue_job failed.
        # Attempt to mark the job as failed, but do not let a secondary
        # DynamoDB error hide the original submission failure.
        try:
            update_job(
                job_id,
                status="FAILED",
                progress="Unable to submit the generation job",
                error_message=(
                    "The job could not be submitted to the processing queue."
                ),
            )

        except Exception:
            logger.exception(
                "Unable to update failed job record. job_id=%s",
                job_id,
            )

        return render_submission_error(
            message=(
                "The generation job could not be submitted. "
                "Please review the service logs and try again."
            ),
            status_code=500,
            job_id=job_id,
        )


@app.get("/jobs/<job_id>")
def job_status_page(job_id: str):
    """
    Display the browser status page for a generation job.
    """
    job = get_job(job_id)

    if job is None:
        abort(
            404,
            description="The requested generation job was not found.",
        )

    return render_template(
        "job_status.html",
        job=job,
        job_id=job_id,
    )


@app.get("/jobs/<job_id>/download")
def download_job(job_id: str):
    return redirect_to_job_download(
        job_id=job_id,
        s3_key_field="s3_key",
        missing_file_message=(
            "The job completed, but no generated application ZIP "
            "was registered for download."
        ),
    )


@app.get("/jobs/<job_id>/reports/download")
def download_job_reports(job_id: str):
    return redirect_to_job_download(
        job_id=job_id,
        s3_key_field="reports_s3_key",
        missing_file_message=(
            "The job completed, but no generation reports ZIP "
            "was registered for download."
        ),
    )


# ---------------------------------------------------------------------------
# JSON API routes
# ---------------------------------------------------------------------------

@app.get("/api/jobs/<job_id>")
def job_status_api(job_id: str):
    """
    Return the current generation-job status as JSON.

    The browser status page polls this endpoint periodically.
    """
    job = get_job(job_id)

    if job is None:
        return jsonify(
            {
                "error": "Job not found",
                "job_id": job_id,
            }
        ), 404

    status = job.get(
        "status",
        "UNKNOWN",
    )

    return jsonify(
        {
            "job_id": job.get(
                "job_id",
                job_id,
            ),
            "status": status,
            "progress": job.get(
                "progress",
                "",
            ),
            "current_stage": job.get(
                "current_stage",
            ),
            "created_at": job.get(
                "created_at",
            ),
            "updated_at": job.get(
                "updated_at",
            ),
            "error_message": job.get(
                "error_message",
            ),
            "download_available": (
                status == "COMPLETED"
                and bool(job.get("s3_key"))
            ),
            "download_url": (
                url_for(
                    "download_job",
                    job_id=job_id,
                )
                if (
                    status == "COMPLETED"
                    and job.get("s3_key")
                )
                else None
            ),
            "reports_download_available": (
                status == "COMPLETED"
                and bool(job.get("reports_s3_key"))
            ),
            "reports_download_url": (
                url_for(
                    "download_job_reports",
                    job_id=job_id,
                )
                if (
                    status == "COMPLETED"
                    and job.get("reports_s3_key")
                )
                else None
            ),
        }
    )


# ---------------------------------------------------------------------------
# HTTP error handlers
# ---------------------------------------------------------------------------

@app.errorhandler(404)
def handle_not_found(error):
    """
    Return a clear response for unavailable routes, jobs, or artefacts.
    """
    message = getattr(
        error,
        "description",
        "The requested resource was not found.",
    )

    return message, 404


@app.errorhandler(409)
def handle_conflict(error):
    """
    Return a clear response when a requested operation is not yet valid.

    For example, a user may request a download before the generation job
    has completed.
    """
    message = getattr(
        error,
        "description",
        "The requested operation cannot be completed yet.",
    )

    return message, 409


@app.errorhandler(413)
def handle_request_too_large(error):
    """
    Handle requests larger than Flask's configured maximum size.
    """
    del error

    return render_submission_error(
        message=(
            "The submitted request is too large. "
            "Please shorten the software requirement and try again."
        ),
        status_code=413,
    )


@app.errorhandler(500)
def handle_internal_server_error(error):
    """
    Return a safe response for unexpected server errors.

    Internal exception details are written to application logs and are
    not exposed to browser users.
    """
    message = getattr(
        error,
        "description",
        "An unexpected server error occurred.",
    )

    return message, 500


# ---------------------------------------------------------------------------
# Local development entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    host = os.getenv(
        "HOST",
        "0.0.0.0",
    )

    port = int(
        os.getenv(
            "PORT",
            "8000",
        )
    )

    logger.info(
        "Starting local Flask web service on %s:%s",
        host,
        port,
    )

    app.run(
        host=host,
        port=port,
        debug=False,
        use_reloader=False,
    )
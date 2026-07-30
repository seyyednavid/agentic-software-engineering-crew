"""
Path utilities for generated application files.

The output directory is resolved at runtime so each SQS job can use its
own isolated workspace.
"""

import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]


def get_output_root() -> Path:
    """
    Return the active output directory.

    In the ECS worker, OUTPUT_DIR points to a job-specific directory such as:

        /app/outputs/jobs/<job_id>

    During ordinary local execution, it defaults to:

        <project>/outputs
    """
    configured_output_dir = os.getenv("OUTPUT_DIR")

    if configured_output_dir:
        return Path(configured_output_dir).resolve()

    return (PROJECT_ROOT / "outputs").resolve()


def get_generated_app_root() -> Path:
    """
    Return the generated application directory for the active job.
    """
    return (get_output_root() / "generated_app").resolve()


def ensure_directory(path: Path) -> Path:
    """
    Create a directory if it does not already exist.
    """
    path.mkdir(
        parents=True,
        exist_ok=True,
    )
    return path


def resolve_safe_path(
    relative_path: str,
    base_directory: Path | None = None,
) -> Path:
    """
    Resolve a relative path and ensure it remains inside the active
    generated application directory.

    The base directory is calculated when this function runs, rather than
    when the Python module is imported.

    Raises:
        ValueError:
            If the path is empty, absolute, or escapes the allowed directory.
    """
    if not relative_path or not relative_path.strip():
        raise ValueError(
            "A non-empty relative path is required."
        )

    relative_path_object = Path(
        relative_path.strip()
    )

    if relative_path_object.is_absolute():
        raise ValueError(
            f"Absolute paths are not allowed: {relative_path}"
        )

    active_base_directory = (
        base_directory
        if base_directory is not None
        else get_generated_app_root()
    ).resolve()

    target_path = (
        active_base_directory
        / relative_path_object
    ).resolve()

    try:
        target_path.relative_to(
            active_base_directory
        )
    except ValueError as exc:
        raise ValueError(
            f"Unsafe path rejected: {relative_path}"
        ) from exc

    return target_path
import os
import shutil
import stat
import time
from pathlib import Path

from flask import Flask, render_template, request, send_file

from src.agentic_software_engineering_crew.crew import AgenticSoftwareEngineeringCrew


app = Flask(__name__)


BASE_DIR = Path(__file__).resolve().parent
OUTPUTS_DIR = BASE_DIR / "outputs"
GENERATED_APP_DIR = OUTPUTS_DIR / "generated_app"
GENERATED_ZIP_PATH = OUTPUTS_DIR / "generated_app.zip"


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
"""


def handle_remove_readonly(func, path, exc_info):
    """
    Allows shutil.rmtree to remove read-only files/folders on Windows.
    Useful when files are created by tools, editors, or sync services.
    """
    try:
        os.chmod(path, stat.S_IWRITE)
        func(path)
    except Exception:
        raise


def remove_outputs_folder():
    """
    Remove the entire outputs folder so every generation starts from scratch.

    This deletes:
    - previous generated app
    - previous ZIP file
    - previous markdown reports
    - any old output artefacts
    """
    if not OUTPUTS_DIR.exists():
        return

    last_error = None

    for attempt in range(8):
        try:
            shutil.rmtree(
                OUTPUTS_DIR,
                onerror=handle_remove_readonly,
            )
            return
        except PermissionError as error:
            last_error = error
            print(f"Attempt {attempt + 1}: outputs folder is locked: {error}")
            time.sleep(1)

    raise PermissionError(
        "Could not delete the outputs folder. "
        "Close any running generated app, terminal, VS Code preview, File Explorer window, "
        "pytest process, or OneDrive sync using the outputs folder, then try again. "
        f"Original error: {last_error}"
    )


def prepare_output_folders():
    """
    Prepare a completely clean output workspace for a new generation.
    """
    remove_outputs_folder()

    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    GENERATED_APP_DIR.mkdir(parents=True, exist_ok=True)


def create_generated_app_zip():
    """
    Create a ZIP file from the generated application folder.
    Returns the ZIP file path if successful, otherwise None.
    """
    if not GENERATED_APP_DIR.exists():
        print("Generated app folder does not exist. ZIP file was not created.")
        return None

    has_files = any(
        file_path.is_file()
        for file_path in GENERATED_APP_DIR.rglob("*")
    )

    if not has_files:
        print("Generated app folder is empty. ZIP file was not created.")
        return None

    if GENERATED_ZIP_PATH.exists():
        GENERATED_ZIP_PATH.unlink()

    zip_file_path = shutil.make_archive(
        base_name=str(OUTPUTS_DIR / "generated_app"),
        format="zip",
        root_dir=str(GENERATED_APP_DIR),
    )

    return zip_file_path


@app.route("/", methods=["GET"])
def index():
    return render_template(
        "generator_index.html",
        default_requirement=DEFAULT_REQUIREMENT,
    )


@app.route("/generate", methods=["POST"])
def generate():
    software_requirement = request.form.get("software_requirement", "").strip()

    if not software_requirement:
        software_requirement = DEFAULT_REQUIREMENT

    try:
        prepare_output_folders()

        inputs = {
            "software_requirement": software_requirement,
        }

        result = AgenticSoftwareEngineeringCrew().crew().kickoff(inputs=inputs)

        zip_file_path = create_generated_app_zip()

        final_result = result.raw if hasattr(result, "raw") else str(result)
        generation_success = zip_file_path is not None

        return render_template(
            "generator_result.html",
            final_result=final_result,
            zip_available=generation_success,
            generation_success=generation_success,
        )

    except Exception as error:
        print(f"Generation failed: {error}")

        return render_template(
            "generator_result.html",
            final_result=f"Generation failed: {error}",
            zip_available=False,
            generation_success=False,
        ), 500


@app.route("/download", methods=["GET"])
def download():
    if not GENERATED_ZIP_PATH.exists():
        return "ZIP file not found. Please generate an app first.", 404

    return send_file(
        GENERATED_ZIP_PATH,
        as_attachment=True,
        download_name="generated_app.zip",
    )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))

    app.run(
        host="0.0.0.0",
        port=port,
        debug=False,
        use_reloader=False,
    )

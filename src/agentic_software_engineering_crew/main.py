import os
import shutil
import warnings


from agentic_software_engineering_crew.crew import AgenticSoftwareEngineeringCrew

warnings.filterwarnings("ignore", category=SyntaxWarning, module="pysbd")


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


def prepare_output_folders():
    """
    Prepare fresh output folders for each new crew run.
    """

    os.makedirs("outputs", exist_ok=True)

    generated_app_path = "outputs/generated_app"

    if os.path.exists(generated_app_path):
        shutil.rmtree(generated_app_path)

    os.makedirs(generated_app_path, exist_ok=True)


def get_user_requirement():
    """
    Ask the user for a software requirement.
    If the user does not provide one, use the default example.
    """

    print("\n=== Agentic Software Engineering Crew ===")
    print("Enter your software requirement.")
    print("Press Enter without typing anything to use the default queue-management example.\n")

    user_input = input("> ").strip()

    if user_input:
        return user_input

    return DEFAULT_REQUIREMENT



def create_generated_app_zip():
    """
    Create a ZIP file from the generated application folder.
    """

    generated_app_path = "outputs/generated_app"
    zip_base_path = "outputs/generated_app"
    existing_zip_path = "outputs/generated_app.zip"

    if not os.path.exists(generated_app_path):
        print("Generated app folder does not exist. ZIP file was not created.")
        return None

    if os.path.exists(existing_zip_path):
        os.remove(existing_zip_path)

    zip_file_path = shutil.make_archive(
        base_name=zip_base_path,
        format="zip",
        root_dir=generated_app_path,
    )

    return zip_file_path



def run():
    """
    Run the Agentic Software Engineering Crew.
    """

    prepare_output_folders()

    software_requirement = get_user_requirement()

    inputs = {
        "software_requirement": software_requirement
    }

    result = AgenticSoftwareEngineeringCrew().crew().kickoff(inputs=inputs)
    
    zip_file_path = create_generated_app_zip()

    print("\n=== Crew Execution Completed ===")
    print("Generated markdown reports are saved in:")
    print("outputs/")

    print("\nGenerated runnable app files are saved in:")
    print("outputs/generated_app/")

    print("\nTo run the generated app:")
    print("cd outputs/generated_app")
    print("python app.py")

    print("\nTo run the generated tests:")
    print("cd outputs/generated_app")
    print("python -m pytest tests/test_app.py")

    print("\n=== Final Result ===")
    print(result.raw if hasattr(result, "raw") else result)
    
    if zip_file_path:
        print("\nGenerated ZIP file saved at:")
        print(zip_file_path)


if __name__ == "__main__":
    run()
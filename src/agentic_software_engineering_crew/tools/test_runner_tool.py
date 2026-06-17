import os
import subprocess
from typing import Type
import sys

from crewai.tools import BaseTool
from pydantic import BaseModel, Field


class TestRunnerToolInput(BaseModel):
    """Input schema for TestRunnerTool."""

    test_path: str = Field(
        default="tests/test_app.py",
        description=(
            "Relative pytest path inside outputs/generated_app. "
            "Example: tests/test_app.py"
        ),
    )


class TestRunnerTool(BaseTool):
    name: str = "Test Runner Tool"
    description: str = (
        "Runs pytest inside outputs/generated_app and returns the full test output. "
        "Use this tool after the generated app and tests have been created."
    )
    args_schema: Type[BaseModel] = TestRunnerToolInput

    def _run(self, test_path: str = "tests/test_app.py") -> str:
        base_dir = os.path.abspath("outputs/generated_app")

        if not os.path.exists(base_dir):
            return "Error: outputs/generated_app does not exist."

        test_target = os.path.join(base_dir, test_path)

        if not os.path.exists(test_target):
            return f"Error: test file does not exist: {test_target}"

        env = os.environ.copy()
        env["PYTHONPATH"] = base_dir + os.pathsep + env.get("PYTHONPATH", "")

        try:
            result = subprocess.run(
                [sys.executable, "-m", "pytest", test_path, "-q"],
                cwd=base_dir,
                capture_output=True,
                text=True,
                timeout=120,
                env=env,
            )

            output = []
            output.append(f"Return code: {result.returncode}")
            output.append("\nSTDOUT:\n")
            output.append(result.stdout)
            output.append("\nSTDERR:\n")
            output.append(result.stderr)

            return "\n".join(output)

        except subprocess.TimeoutExpired:
            return "Error: pytest execution timed out after 120 seconds."
        except Exception as e:
            return f"Error while running pytest: {e}"
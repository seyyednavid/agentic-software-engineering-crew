"""
CrewAI tool for running pytest against the generated application.

The tool resolves the active generated application directory at runtime,
allowing each SQS job to use an isolated output workspace.
"""

import os
import subprocess
import sys

from crewai.tools import BaseTool
from pydantic import BaseModel, Field

from .path_utils import (
    get_generated_app_root,
    resolve_safe_path,
)


class TestRunnerInput(BaseModel):
    """
    Input schema for the generated application test runner.
    """

    test_path: str = Field(
        default="tests",
        description=(
            "Relative test file or directory inside "
            "the active generated application."
        ),
    )


class TestRunnerTool(BaseTool):
    """
    Run pytest for files inside the active generated application.
    """

    name: str = "Test Runner Tool"

    description: str = (
        "Runs pytest against tests inside the active generated "
        "application directory and returns the test result."
    )

    args_schema: type[BaseModel] = TestRunnerInput

    def _run(
        self,
        test_path: str = "tests",
    ) -> str:
        """
        Run pytest against a validated test path.

        Pytest plugin auto-loading is disabled to prevent unrelated
        third-party plugins from affecting generated-app tests.
        """
        try:
            generated_app_root = (
                get_generated_app_root()
            )

            resolved_test_path = resolve_safe_path(
                test_path,
                base_directory=generated_app_root,
            )

            if not generated_app_root.exists():
                return (
                    "Generated application directory not found: "
                    f"{generated_app_root}"
                )

            if not resolved_test_path.exists():
                return (
                    f"Test path not found: {test_path}"
                )

            if not (
                resolved_test_path.is_file()
                or resolved_test_path.is_dir()
            ):
                return (
                    f"Invalid test path: {test_path}"
                )

            command = [
                sys.executable,
                "-m",
                "pytest",
                str(resolved_test_path),
                "-q",
            ]

            test_environment = os.environ.copy()

            # Prevent unrelated pytest plugins from loading.
            test_environment[
                "PYTEST_DISABLE_PLUGIN_AUTOLOAD"
            ] = "1"

            # Make generated application modules importable.
            existing_pythonpath = test_environment.get(
                "PYTHONPATH",
                "",
            )

            python_paths = [
                str(generated_app_root),
            ]

            if existing_pythonpath:
                python_paths.append(
                    existing_pythonpath
                )

            test_environment["PYTHONPATH"] = (
                os.pathsep.join(python_paths)
            )

            # Prevent generated tests from accessing parent application
            # credentials.
            test_environment.pop(
                "OPENAI_API_KEY",
                None,
            )
            test_environment.pop(
                "OPENROUTER_API_KEY",
                None,
            )
            test_environment.pop(
                "OPENROUTER_API_BASE",
                None,
            )

            result = subprocess.run(
                command,
                cwd=generated_app_root,
                capture_output=True,
                text=True,
                timeout=180,
                check=False,
                env=test_environment,
            )

            return (
                f"Working directory: {generated_app_root}\n"
                f"Return code: {result.returncode}\n\n"
                f"STDOUT:\n{result.stdout}\n\n"
                f"STDERR:\n{result.stderr}"
            )

        except subprocess.TimeoutExpired:
            return (
                "Test execution stopped after the "
                "180-second timeout."
            )

        except ValueError as error:
            return (
                f"Test path rejected: {error}"
            )

        except OSError as error:
            return (
                f"Unable to run tests: {error}"
            )
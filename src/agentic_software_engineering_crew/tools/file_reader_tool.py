import os
from typing import Type

from crewai.tools import BaseTool
from pydantic import BaseModel, Field


class FileReaderToolInput(BaseModel):
    """Input schema for FileReaderTool."""

    file_path: str = Field(
        ...,
        description=(
            "Relative file path inside outputs/generated_app. "
            "Example: app.py, tests/test_app.py, templates/index.html"
        ),
    )


class FileReaderTool(BaseTool):
    name: str = "File Reader Tool"
    description: str = (
        "Reads files from outputs/generated_app. Use this tool when you need to inspect "
        "generated source code, frontend files, or tests before debugging."
    )
    args_schema: Type[BaseModel] = FileReaderToolInput

    def _run(self, file_path: str) -> str:
        base_dir = os.path.abspath("outputs/generated_app")
        target_path = os.path.abspath(os.path.join(base_dir, file_path))

        if not target_path.startswith(base_dir):
            return f"Error: unsafe file path rejected: {file_path}"

        if not os.path.exists(target_path):
            return f"Error: file does not exist: {target_path}"

        with open(target_path, "r", encoding="utf-8") as file:
            return file.read()
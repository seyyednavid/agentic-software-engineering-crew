import os
from typing import Type

from crewai.tools import BaseTool
from pydantic import BaseModel, Field


class FileWriterToolInput(BaseModel):
    """Input schema for FileWriterTool."""

    file_path: str = Field(
        ...,
        description=(
            "Relative file path inside outputs/generated_app. "
            "Example: app.py, templates/index.html, static/style.css, tests/test_app.py"
        ),
    )
    content: str = Field(
        ...,
        description="The complete content that should be written into the file.",
    )


class FileWriterTool(BaseTool):
    name: str = "File Writer Tool"
    description: str = (
        "Writes real project files into the outputs/generated_app directory. "
        "Use this tool when you need to create runnable application files such as "
        "app.py, HTML templates, CSS files, requirements.txt, README.md, or test files."
    )
    args_schema: Type[BaseModel] = FileWriterToolInput

    def _run(self, file_path: str, content: str) -> str:
        base_dir = os.path.abspath("outputs/generated_app")
        target_path = os.path.abspath(os.path.join(base_dir, file_path))

        # Prevent writing outside outputs/generated_app
        if not target_path.startswith(base_dir):
            return f"Error: unsafe file path rejected: {file_path}"

        os.makedirs(os.path.dirname(target_path), exist_ok=True)

        with open(target_path, "w", encoding="utf-8") as file:
            file.write(content)

        return f"File written successfully: {target_path}"
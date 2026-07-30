from crewai.tools import BaseTool
from pydantic import BaseModel, Field

from .path_utils import resolve_safe_path


class FileReaderInput(BaseModel):
    file_path: str = Field(
        ...,
        description="Relative file path  inside the active generated application",
    )


class FileReaderTool(BaseTool):
    name: str = "File Reader Tool"
    description: str = (
        "Reads a UTF-8 text file from the active generated application."
    )
    args_schema: type[BaseModel] = FileReaderInput

    def _run(self, file_path: str) -> str:
        try:
            target_path = resolve_safe_path(file_path)

            if not target_path.exists():
                return f"File not found: {file_path}"

            if not target_path.is_file():
                return f"Path is not a file: {file_path}"

            return target_path.read_text(encoding="utf-8")

        except ValueError as exc:
            return f"File read rejected: {exc}"

        except UnicodeDecodeError:
            return f"File is not valid UTF-8 text: {file_path}"

        except OSError as exc:
            return f"File read failed: {exc}"
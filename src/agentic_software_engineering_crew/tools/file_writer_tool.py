from crewai.tools import BaseTool
from pydantic import BaseModel, Field

from .path_utils import ensure_directory, resolve_safe_path


class FileWriterInput(BaseModel):
    file_path: str = Field(
        ...,
        description="Relative file path inside the active generated application",
    )
    content: str = Field(
        ...,
        description="Complete content to write to the file",
    )


class FileWriterTool(BaseTool):
    name: str = "File Writer Tool"
    description: str = (
        "Writes a file inside the active generated application. "
        "Only safe relative paths are allowed."
    )
    args_schema: type[BaseModel] = FileWriterInput

    def _run(self, file_path: str, content: str) -> str:
        try:
            target_path = resolve_safe_path(file_path)
            ensure_directory(target_path.parent)

            target_path.write_text(
                content,
                encoding="utf-8",
            )

            return f"File written successfully: {file_path}"

        except ValueError as exc:
            return f"File write rejected: {exc}"

        except OSError as exc:
            return f"File write failed: {exc}"
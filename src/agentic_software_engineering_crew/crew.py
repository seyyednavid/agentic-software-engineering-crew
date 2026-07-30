import logging
import os
from collections.abc import Callable
from typing import Any

from crewai import Agent, Crew, Process, Task
from crewai.project import CrewBase, agent, crew, task

from agentic_software_engineering_crew.tools.file_writer_tool import FileWriterTool
from agentic_software_engineering_crew.tools.file_reader_tool import FileReaderTool
from agentic_software_engineering_crew.tools.test_runner_tool import TestRunnerTool
from agentic_software_engineering_crew.services.job_store import update_job


logger = logging.getLogger(__name__)


def stage_callback(next_stage: str | None, progress: str) -> Callable[[Any], None]:
    """Update DynamoDB when a sequential task finishes."""
    def callback(_task_output: Any) -> None:
        job_id = os.getenv("CURRENT_JOB_ID")
        if not job_id:
            logger.warning("CURRENT_JOB_ID is missing; stage update skipped.")
            return
        try:
            update_job(
                job_id,
                current_stage=next_stage,
                progress=progress,
            )
        except Exception:
            logger.exception(
                "Unable to update job stage. job_id=%s next_stage=%s",
                job_id,
                next_stage,
            )
    return callback


@CrewBase
class AgenticSoftwareEngineeringCrew:
    """Agentic Software Engineering Crew"""

    agents_config = "config/agents.yaml"
    tasks_config = "config/tasks.yaml"

    @agent
    def requirement_analyst(self) -> Agent:
        return Agent(
            config=self.agents_config["requirement_analyst"],
            verbose=False,
        )

    @agent
    def software_architect(self) -> Agent:
        return Agent(
            config=self.agents_config["software_architect"],
            verbose=False,
        )

    @agent
    def backend_engineer(self) -> Agent:
        return Agent(
            config=self.agents_config["backend_engineer"],
            tools=[
                FileWriterTool(),
            ],
            verbose=False,
        )

    @agent
    def frontend_engineer(self) -> Agent:
        return Agent(
            config=self.agents_config["frontend_engineer"],
            tools=[
                FileWriterTool(),
            ],
            verbose=False,
        )

    @agent
    def test_engineer(self) -> Agent:
        return Agent(
            config=self.agents_config["test_engineer"],
            tools=[
                FileWriterTool(),
            ],
            verbose=False,
        )

    @agent
    def debugging_engineer(self) -> Agent:
        return Agent(
            config=self.agents_config["debugging_engineer"],
            tools=[
                FileReaderTool(),
                FileWriterTool(),
                TestRunnerTool(),
            ],
            verbose=False,
        )

    @agent
    def code_reviewer(self) -> Agent:
        return Agent(
            config=self.agents_config["code_reviewer"],
            tools=[
                FileReaderTool(),
            ],
            verbose=False,
        )

    @task
    def analyse_requirements_task(self) -> Task:
        return Task(
            config=self.tasks_config["analyse_requirements_task"],
            callback=stage_callback(
                "architecture",
                "Designing the application architecture",
            ),
        )

    @task
    def design_architecture_task(self) -> Task:
        return Task(
            config=self.tasks_config["design_architecture_task"],
            callback=stage_callback(
                "backend",
                "Generating backend files",
            ),
        )

    @task
    def generate_backend_files_task(self) -> Task:
        return Task(
            config=self.tasks_config["generate_backend_files_task"],
            callback=stage_callback(
                "frontend",
                "Generating frontend files",
            ),
        )

    @task
    def generate_frontend_files_task(self) -> Task:
        return Task(
            config=self.tasks_config["generate_frontend_files_task"],
            callback=stage_callback(
                "testing",
                "Generating automated tests",
            ),
        )

    @task
    def generate_test_files_task(self) -> Task:
        return Task(
            config=self.tasks_config["generate_test_files_task"],
            callback=stage_callback(
                "debugging",
                "Running tests and debugging the application",
            ),
        )

    @task
    def run_and_debug_tests_task(self) -> Task:
        return Task(
            config=self.tasks_config["run_and_debug_tests_task"],
            callback=stage_callback(
                "review",
                "Reviewing the generated application",
            ),
        )

    @task
    def review_generated_application_task(self) -> Task:
        return Task(
            config=self.tasks_config["review_generated_application_task"],
            callback=stage_callback(
                None,
                "Preparing the generated application package",
            ),
        )

    @crew
    def crew(self) -> Crew:
        """Creates the Agentic Software Engineering Crew"""

        return Crew(
            agents=self.agents,
            tasks=self.tasks,
            process=Process.sequential,
            verbose=False,
        )
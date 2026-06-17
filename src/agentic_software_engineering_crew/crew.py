from crewai import Agent, Crew, Process, Task
from crewai.project import CrewBase, agent, crew, task

from agentic_software_engineering_crew.tools.file_writer_tool import FileWriterTool
from agentic_software_engineering_crew.tools.file_reader_tool import FileReaderTool
from agentic_software_engineering_crew.tools.test_runner_tool import TestRunnerTool


@CrewBase
class AgenticSoftwareEngineeringCrew:
    """Agentic Software Engineering Crew"""

    agents_config = "config/agents.yaml"
    tasks_config = "config/tasks.yaml"

    @agent
    def requirement_analyst(self) -> Agent:
        return Agent(
            config=self.agents_config["requirement_analyst"],
            verbose=True,
        )

    @agent
    def software_architect(self) -> Agent:
        return Agent(
            config=self.agents_config["software_architect"],
            verbose=True,
        )

    @agent
    def backend_engineer(self) -> Agent:
        return Agent(
            config=self.agents_config["backend_engineer"],
            tools=[
                FileWriterTool(),
            ],
            verbose=True,
        )

    @agent
    def frontend_engineer(self) -> Agent:
        return Agent(
            config=self.agents_config["frontend_engineer"],
            tools=[
                FileWriterTool(),
            ],
            verbose=True,
        )

    @agent
    def test_engineer(self) -> Agent:
        return Agent(
            config=self.agents_config["test_engineer"],
            tools=[
                FileWriterTool(),
            ],
            verbose=True,
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
            verbose=True,
            allow_code_execution=True,
            code_execution_mode="safe",
            max_execution_time=500,
            max_retry_limit=3,
        )

    @agent
    def code_reviewer(self) -> Agent:
        return Agent(
            config=self.agents_config["code_reviewer"],
            tools=[
                FileReaderTool(),
            ],
            verbose=True,
        )

    @task
    def analyse_requirements_task(self) -> Task:
        return Task(
            config=self.tasks_config["analyse_requirements_task"]
        )

    @task
    def design_architecture_task(self) -> Task:
        return Task(
            config=self.tasks_config["design_architecture_task"]
        )

    @task
    def generate_backend_files_task(self) -> Task:
        return Task(
            config=self.tasks_config["generate_backend_files_task"]
        )

    @task
    def generate_frontend_files_task(self) -> Task:
        return Task(
            config=self.tasks_config["generate_frontend_files_task"]
        )

    @task
    def generate_test_files_task(self) -> Task:
        return Task(
            config=self.tasks_config["generate_test_files_task"]
        )

    @task
    def run_and_debug_tests_task(self) -> Task:
        return Task(
            config=self.tasks_config["run_and_debug_tests_task"]
        )

    @task
    def review_generated_application_task(self) -> Task:
        return Task(
            config=self.tasks_config["review_generated_application_task"]
        )

    @crew
    def crew(self) -> Crew:
        """Creates the Agentic Software Engineering Crew"""

        return Crew(
            agents=self.agents,
            tasks=self.tasks,
            process=Process.sequential,
            verbose=True,
        )
"""Harbor wrapper for Vals AI's Finance Agent v2 (FA v2), the FrontierFinance parity agent.

FA v2 runs one question per process in its single-task mode and writes
``<output-dir>/<task-id>/generation.json`` with ``status`` and ``data`` (the final
answer). The wrapper copies ``data`` to ``/app/report.md`` for the verifier.

Usage (from the adapters repo root):

    PYTHONPATH=src/frontier-finance/src harbor trial start \
        -p datasets/frontier-finance/<task> \
        -a frontier_finance.finance_agent_v2:FinanceAgentV2 \
        -m <model-library id> --agent-timeout 7800
"""

from __future__ import annotations

import json
import shlex
import shutil

from harbor.agents.installed.base import BaseInstalledAgent
from harbor.environments.base import BaseEnvironment
from harbor.models.agent.context import AgentContext

from frontier_finance.fa2_shared import (
    FA2_COMMIT,
    FA2_MAX_TIME,
    FA2_PYTHON,
    FA2_REPO,
    FA2_UV_VERSION,
    question_from_instruction,
)

FA2_DIR = "/opt/finance-agent-v2"
FA2_RUN_DIR = "/logs/agent/fa2"
REPORT = "/app/report.md"

# Model endpoint, provider and tool keys FA v2 reads from its environment.
FORWARDED_ENV = (
    "CUSTOM_ENDPOINT",
    "CUSTOM_API_KEY",
    "OPENAI_API_KEY",
    "OPENAI_BASE_URL",
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_BASE_URL",
    "GOOGLE_API_KEY",
    "DEEPSEEK_API_KEY",
    "TAVILY_API_KEY",
    "SEC_EDGAR_API_KEY",
    "PRICING_DATA_API_KEY",
)

# Exit 3 on status "error" so Harbor records the trial as an agent failure; the
# report is written first, so the trial is still graded (empty answer -> 0).
_COPY_ANSWER = f"""
import json, pathlib, sys
gen = json.loads(pathlib.Path("{FA2_RUN_DIR}/task/generation.json").read_text())
pathlib.Path("{REPORT}").write_text(gen["data"])
print("fa2 status:", gen["status"], "answer chars:", len(gen["data"]))
sys.exit(3 if gen["status"] == "error" else 0)
"""


class FinanceAgentV2(BaseInstalledAgent):
    def __init__(self, *args, max_time: int = FA2_MAX_TIME, max_turns: int | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self._max_time = max_time
        self._max_turns = max_turns

    @staticmethod
    def name() -> str:
        return "finance-agent-v2"

    def version(self) -> str | None:
        return FA2_COMMIT

    async def install(self, environment: BaseEnvironment) -> None:
        await self.ensure_system_dependencies(environment, ("git",))
        # Install from FA v2's own uv.lock so both parity sides get identical packages.
        # The lockfile's [options] table needs uv >= 0.13; the image's uv is older.
        await self.exec_as_root(
            environment,
            command=(
                f"set -euo pipefail; "
                f"rm -rf {FA2_DIR} && git clone -q {FA2_REPO} {FA2_DIR} && "
                f"git -C {FA2_DIR} checkout -q {FA2_COMMIT} && "
                f"pip install -q --no-cache-dir --target {FA2_DIR}/.uv uv=={FA2_UV_VERSION} && "
                f"cd {FA2_DIR} && UV_PROJECT_ENVIRONMENT={FA2_DIR}/.venv "
                f"{FA2_DIR}/.uv/bin/uv sync --frozen --no-dev --no-editable -q --python {FA2_PYTHON} && "
                f"chmod -R a+rX {FA2_DIR}"
            ),
        )

    async def run(self, instruction: str, environment: BaseEnvironment, context: AgentContext) -> None:
        if not self.model_name:
            raise ValueError("FinanceAgentV2 needs a model name (-m)")

        question = self.logs_dir / "question.txt"
        question.write_text(question_from_instruction(instruction))
        await self.exec_as_agent(environment, command=f"mkdir -p {FA2_RUN_DIR}")
        await environment.upload_file(source_path=question, target_path=f"{FA2_RUN_DIR}/question.txt")

        env = {key: value for key in FORWARDED_ENV if (value := self._get_env(key))}
        turns = f"--max-turns {self._max_turns} " if self._max_turns else ""
        # cd to an empty directory: FA v2 loads ./.env, which must not exist here.
        await self.exec_as_agent(
            environment,
            command=(
                f"mkdir -p {FA2_RUN_DIR}/cwd && cd {FA2_RUN_DIR}/cwd && "
                f"{FA2_DIR}/.venv/bin/finance-agent "
                f"--model {shlex.quote(self.model_name)} "
                f"--question-file {FA2_RUN_DIR}/question.txt --task-id task "
                f"--output-dir {FA2_RUN_DIR} --log-dir {FA2_RUN_DIR}/logs "
                f"--max-time {self._max_time} {turns}"
                f"2>&1 | tee {FA2_RUN_DIR}/finance-agent.txt"
            ),
            env=env,
        )
        await self.exec_as_agent(environment, command=f"python3 -c {shlex.quote(_COPY_ANSWER)}")

    def populate_context_post_run(self, context: AgentContext) -> None:
        run_dir = next((self.logs_dir / "fa2" / "logs").glob("*/*/*/task"), None)
        if run_dir is None:
            return
        atif = run_dir / "trajectory_atif.json"
        if atif.is_file():
            shutil.copyfile(atif, self.logs_dir / "trajectory.json")
        result = run_dir / "result.json"
        if result.is_file():
            usage = json.loads(result.read_text()).get("final_aggregated_metadata") or {}
            context.n_input_tokens = usage.get("total_input_tokens") or 0
            context.n_output_tokens = usage.get("total_output_tokens") or 0
            context.n_cache_tokens = usage.get("cache_read_tokens") or 0
            context.cost_usd = usage.get("cost")

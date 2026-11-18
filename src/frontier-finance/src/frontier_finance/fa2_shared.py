"""What both FrontierFinance parity sides share about Finance Agent v2 (FA v2): pins and the question text."""

FA2_REPO = "https://github.com/vals-ai/finance-agent-v2.git"
FA2_COMMIT = "3ef5e4a"
# FA v2's uv.lock has an [options] table that needs uv >= 0.13.
FA2_UV_VERSION = "0.13.7"
FA2_PYTHON = "3.13"
FA2_MAX_TIME = 7200

# FA v2 statuses that are real results. "error" and a missing generation.json are
# infrastructure failures, rerun before reporting.
FINAL_STATUSES = frozenset({"success", "max_time", "max_turns"})

# Everything after this marker in instruction.md asks for /app/report.md, which FA v2
# cannot write; it answers through its own submit tool instead.
REPORT_INSTRUCTIONS_MARKER = "\n\nResearch the query using any sources you can access"


def question_from_instruction(instruction: str) -> str:
    """The part of instruction.md both parity sides pass to FA v2: role, query and date."""
    head, sep, _ = instruction.partition(REPORT_INSTRUCTIONS_MARKER)
    if not sep:
        raise ValueError("instruction.md does not contain the report instructions marker")
    return head.strip()

"""Original side of FrontierFinance parity: Finance Agent v2 (FA v2) outside Harbor.

  run      Install the pinned FA v2 from its uv.lock and run its single-task mode once
           per query, with the same question text, model and limits as the Harbor
           wrapper. Rerunning the same command skips queries that already have a
           final status and retries the rest (status "error" or no generation.json).
  collect  Count trials by FA v2 status and write upstream's system_summaries.json.
           Reads an original-side run directory or a Harbor job directory, so the
           same counts and the cross-grade export come from one place.

Usage (from the adapters repo root; keys come from the environment):

  uv run src/frontier-finance/run_original_fa2.py run -d datasets/frontier-finance \\
      -o parity/original/run1 -m deepseek/deepseek-v4-pro -n 8
  uv run src/frontier-finance/run_original_fa2.py collect parity/original/run1 \\
      --summaries parity/original/run1/system_summaries.json

Then grade with the upstream CLI at 8b71342 and eval.example.yaml unchanged:
  frontier-finance-grader --config eval.example.yaml   (responses_path -> the summaries)
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tomllib
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))
from frontier_finance.fa2_shared import (  # noqa: E402
    FA2_COMMIT,
    FA2_MAX_TIME,
    FA2_PYTHON,
    FA2_REPO,
    FA2_UV_VERSION,
    FINAL_STATUSES,
    question_from_instruction,
)

GENERATION = Path("task/generation.json")


def dataset_questions(dataset: Path) -> dict[str, str]:
    questions = {}
    for task in sorted(p for p in dataset.iterdir() if (p / "instruction.md").is_file()):
        query_id = tomllib.loads((task / "task.toml").read_text())["metadata"]["source_query_id"]
        questions[query_id] = question_from_instruction((task / "instruction.md").read_text())
    return questions


def install(fa2_dir: Path) -> Path:
    exe = fa2_dir / ".venv" / "bin" / "finance-agent"
    if exe.exists():
        return exe
    subprocess.run(["git", "clone", "-q", FA2_REPO, str(fa2_dir)], check=True)
    subprocess.run(["git", "-C", str(fa2_dir), "checkout", "-q", FA2_COMMIT], check=True)
    subprocess.run(
        ["uvx", f"uv@{FA2_UV_VERSION}", "sync", "--frozen", "--no-dev", "--no-editable", "-q", "--python", FA2_PYTHON],
        cwd=fa2_dir,
        env={**os.environ, "UV_PROJECT_ENVIRONMENT": str(fa2_dir / ".venv")},
        check=True,
    )
    return exe


def read_status(query_dir: Path) -> tuple[str, str]:
    """(status, answer); status is "missing" when FA v2 wrote no generation.json."""
    gen = query_dir / GENERATION
    if not gen.is_file():
        return "missing", ""
    data = json.loads(gen.read_text())
    return data["status"], data["data"]


def run_one(exe: Path, query_dir: Path, question: str, model: str, max_time: int, max_turns: int | None) -> str:
    if read_status(query_dir)[0] in FINAL_STATUSES:
        return "skipped"
    (query_dir / GENERATION).unlink(missing_ok=True)
    cwd = query_dir / "cwd"  # empty, so FA v2 finds no ./.env
    cwd.mkdir(parents=True, exist_ok=True)
    (query_dir / "question.txt").write_text(question)
    cmd = [
        str(exe),
        "--model",
        model,
        "--question-file",
        str(query_dir / "question.txt"),
        "--task-id",
        "task",
        "--output-dir",
        str(query_dir),
        "--log-dir",
        str(query_dir / "logs"),
        "--max-time",
        str(max_time),
    ]
    if max_turns:
        cmd += ["--max-turns", str(max_turns)]
    with open(query_dir / "finance-agent.txt", "w") as log:
        code = subprocess.run(cmd, cwd=cwd, stdout=log, stderr=subprocess.STDOUT).returncode
    (query_dir / "exit_code").write_text(str(code))
    return read_status(query_dir)[0]


def cmd_run(args: argparse.Namespace) -> None:
    questions = dataset_questions(args.dataset)
    if args.limit:
        questions = dict(list(questions.items())[: args.limit])
    exe = install(args.fa2_dir.resolve())
    out = args.out.resolve()
    with ThreadPoolExecutor(args.concurrency) as pool:
        futures = {
            qid: pool.submit(run_one, exe, out / qid, q, args.model, args.max_time, args.max_turns)
            for qid, q in questions.items()
        }
        for qid, fut in futures.items():
            print(f"{qid}: {fut.result()}", flush=True)
    collect([out], None)


def records(path: Path) -> dict[str, tuple[str, str]]:
    """query_id -> (status, answer) from an original-side run dir or a Harbor job dir."""
    found = {}
    for entry in sorted(p for p in path.iterdir() if p.is_dir()):
        config = entry / "config.json"
        if config.is_file():  # Harbor trial
            qid = Path(json.loads(config.read_text())["task"]["path"]).name.removeprefix("frontier-finance-")
            found[qid] = read_status(entry / "agent" / "fa2")
        elif (entry / "question.txt").is_file():  # original-side query
            found[entry.name] = read_status(entry)
    return found


def collect(paths: list[Path], summaries: Path | None) -> None:
    for path in paths:
        recs = records(path)
        counts = Counter(status for status, _ in recs.values())
        rerun = sorted(q for q, (s, _) in recs.items() if s not in FINAL_STATUSES)
        print(f"== {path}: {len(recs)} queries  " + "  ".join(f"{k}={v}" for k, v in sorted(counts.items())))
        if rerun:
            print(f"   to rerun ({len(rerun)}): {' '.join(rerun)}")
        if summaries:
            rows = [{"query_id": q, "system_summary": a} for q, (_, a) in sorted(recs.items())]
            summaries.parent.mkdir(parents=True, exist_ok=True)
            summaries.write_text(json.dumps(rows, indent=2))
            print(f"   wrote {len(rows)} summaries to {summaries}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("run", help="run FA v2 on every query outside Harbor")
    p.add_argument("-d", "--dataset", type=Path, required=True, help="generated FrontierFinance tasks")
    p.add_argument("-o", "--out", type=Path, required=True, help="run directory, one subdirectory per query")
    p.add_argument("-m", "--model", required=True, help="FA v2 model id, same as Harbor's -m")
    p.add_argument("-n", "--concurrency", type=int, default=8)
    p.add_argument("--limit", type=int, help="first N queries only (sanity run)")
    p.add_argument("--max-time", type=int, default=FA2_MAX_TIME)
    p.add_argument("--max-turns", type=int)
    p.add_argument("--fa2-dir", type=Path, default=Path("parity/finance-agent-v2"))
    p = sub.add_parser("collect", help="count statuses and write system_summaries.json")
    p.add_argument("paths", type=Path, nargs="+", help="original-side run dirs or Harbor job dirs")
    p.add_argument("--summaries", type=Path, help="write upstream system_summaries.json (one path only)")
    args = parser.parse_args()
    if args.cmd == "run":
        cmd_run(args)
    else:
        if args.summaries and len(args.paths) != 1:
            parser.error("--summaries takes exactly one path")
        collect(args.paths, args.summaries)


if __name__ == "__main__":
    main()

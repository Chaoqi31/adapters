## FrontierFinance → Harbor Adapter

## Overview

FrontierFinance evaluates finance AI agents on open-ended, long-form research questions asked by investment professionals: company research, earnings and events, financial data and modeling, sector/industry/macro analysis, coverage and catalyst monitoring, and screening and discovery. Answers are free-form English reports graded against expert-authored rubrics by an LLM judge panel.

- **Size:** 220 queries with 11,543 rubrics (3 to 475 rubrics per query, median 27; 65% marked `must_have`). This adapter converts **all 220 queries into 220 Harbor tasks** (one task per query). No queries are excluded.
- **Provenance:** [samaya-ai/FrontierFinance](https://huggingface.co/datasets/samaya-ai/FrontierFinance) (Hugging Face dataset, revision `36afd6dc1cbb2c4512536daf917dc28b1225a720`) and the official grader [samaya-ai/frontier-finance](https://github.com/samaya-ai/frontier-finance) (commit `8b71342dc7730eb1803dd3934e17bc71c9922ec5`).
- **License:** dataset CC-BY-4.0, grader Apache-2.0. The dataset is gated on Hugging Face; its terms ask users not to reshare it outside a gated or private repository.
- **Main adaptation:** the original benchmark only grades responses produced by an external system. Here, the query becomes an agent instruction, the agent writes its report to `/app/report.md`, and the verifier runs the unmodified upstream grader on that report.

## What is FrontierFinance?

FrontierFinance ([blog](https://samaya.ai/blog/frontier-finance), [website](https://research.samaya.ai/benchmarks/frontier-finance), [arXiv](https://arxiv.org/abs/2608.11683)) is a benchmark from Samaya AI for measuring the frontier intelligence of finance agents. Each of its 220 expert-crafted queries comes with a date (`query_date`, the temporal anchor for the question) and a set of atomic, verifiable rubrics that a good answer should satisfy. A panel of three judges (Claude Sonnet 4.6, Gemini 3.1 Pro, GPT-5.4) labels each rubric as satisfied or not, and a rubric counts as qualified by majority vote. The headline metric is the **rubric qualification rate**, reported both as a macro average (mean of per-query rates) and a micro average (total qualified / total rubrics), for all rubrics and for the `must_have` subset.

## Adapter Features

- **Data loading:** downloads `frontier_finance_public.jsonl` from Hugging Face at a pinned revision (requires accepting the dataset terms and `hf auth login` / `HF_TOKEN`), or reads a local copy via `--data-path`.
- **Stable task IDs:** `frontier-finance-<query_id>`, using the upstream 16-hex `query_id`; task names are `samaya-ai/frontier-finance__<query_id>`.
- **Unmodified upstream grading:** the Docker image installs the official `frontier-finance` grader at a pinned commit in an isolated virtualenv (`/opt/ff-grader`), using upstream's `uv.lock` so the judge SDK versions (anthropic 0.116.0, google-genai 2.10.0, openai 2.44.0) match upstream. `tests/grade.py` builds the upstream `EvalItem` from the task's rubrics and the agent's report and calls the upstream `Grader` with the judge panel and settings from upstream `eval.example.yaml` (`max_rubrics_per_call=30`, `max_tokens=32000`, `request_timeout=120`, `max_retries=2`, `max_json_parse_retries=1`). Prompts, batching, parsing, and majority voting are the upstream code.
- **Reward:** `reward` in `/logs/verifier/reward.json` is the task's rubric qualification rate, so over trials that produce a reward the Harbor mean equals upstream `macro_avg_qualification_rate_on_all_queries` (see Notes & Caveats for trials without a reward). Per-rubric judgements and the `must_have` qualification rate are written to `/logs/verifier/grading.json`.
- **Rubrics hidden from the agent:** rubrics live only in `tests/`, which Harbor copies in after the agent finishes.
- **Internet access:** the agent needs web access for research, set explicitly with `network_mode = "public"` on the agent and the verifier. The verifier calls the Anthropic, Google, and OpenAI APIs.
- **Separate verifier:** grading runs in a fresh container built from the same image (`[verifier] environment_mode = "separate"`). Only `/app/report.md` is handed over (task-level `artifacts`), so the agent cannot modify the grader. This also lets `harbor regrade` re-grade recorded reports without re-running the agent.

## Generated Task Structure

```
frontier-finance/
├── frontier-finance-<query_id>/
│   ├── task.toml                 # Task config; separate verifier; verifier.env passes judge keys and optional base URLs; verifier timeout sized per task
│   ├── instruction.md            # The query, its date, and the output location (/app/report.md)
│   ├── environment/
│   │   └── Dockerfile            # python:3.13-slim + pinned upstream grader in /opt/ff-grader
│   ├── solution/
│   │   ├── solve.sh              # Copies oracle_report.md to /app/report.md
│   │   └── oracle_report.md      # Reference report assembled from the rubrics
│   └── tests/
│       ├── test.sh               # Runs grade.py with the grader virtualenv
│       ├── grade.py              # Calls the upstream Grader; writes reward.json and grading.json
│       ├── rubrics.jsonl         # This query's record in the upstream JSONL format
│       └── oracle_report.md      # Byte-identical copy used for the oracle shortcut
```

Adapter code layout:

```
src/frontier-finance/
├── README.md
├── adapter_metadata.json
├── judge_calibration.py          # Judge-path check: rotate oracle reports across trials, summarize regrades
├── parity_experiment.json
├── pyproject.toml
├── run_frontier-finance.yaml
└── src/frontier_finance/
    ├── __init__.py
    ├── adapter.py
    ├── main.py
    └── task-template/
        ├── task.toml
        ├── instruction.md
        ├── environment/Dockerfile
        ├── solution/solve.sh
        └── tests/{test.sh,grade.py}
```

## Run Evaluation / Harness

### Running with Datasets Registry

After the dataset is published:

```bash
# Oracle agent (reference solution)
harbor run -d samaya-ai/frontier-finance -a oracle

# A specific agent and model
harbor run -d samaya-ai/frontier-finance -a <agent_name> -m "<model_name>"
```

The verifier needs `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, and `GEMINI_API_KEY` in your environment (or an `--env-file`). `harbor run` checks for them before any trial starts. The Gemini key must be named `GEMINI_API_KEY`; upstream's `GOOGLE_API_KEY` alias is not forwarded. The oracle run never calls the judges, so placeholder values are enough for it.

### Using Job Configurations

```bash
# From the adapters repository root, after generating tasks into datasets/frontier-finance
harbor run -c src/frontier-finance/run_frontier-finance.yaml

# Or point at the generated dataset directly
harbor run -p datasets/frontier-finance -a <agent_name> -m "<model_name>"

# Resume a previously started job
harbor job resume -p /path/to/jobs/directory
```

### Running Individual Trial

```bash
harbor trial start -p datasets/frontier-finance/<task_id>
harbor trial start -p datasets/frontier-finance/<task_id> -a <agent_name> -m "<model_name>"
```

## Usage: Create Task Directories

Accept the dataset terms at https://huggingface.co/datasets/samaya-ai/FrontierFinance, then:

```bash
hf auth login            # or export HF_TOKEN=...
cd src/frontier-finance
uv sync
uv run frontier-finance --output-dir ../../datasets/frontier-finance
```

Available flags:
- `--output-dir`: where to write tasks (default `datasets/frontier-finance` at the repo root)
- `--limit`: generate only the first N tasks (sorted by `query_id`)
- `--overwrite`: overwrite existing task directories
- `--task-ids`: only generate these tasks (upstream `query_id` or local task id)
- `--data-path`: use a local `frontier_finance_public.jsonl` instead of downloading

## Comparison with Original Benchmark (Parity)

Parity experiments have not been run yet; the plan (agent, model, subset size, number of runs) will be agreed with the Harbor team first.

| Agent | Model | Metric | Number of Runs | Dataset Size | Original Benchmark Performance | Harbor Adapter Performance |
|-------|-------|--------|------------------|--------------|------------------------------|----------------------------|
| TBD | TBD | Macro rubric qualification rate | TBD | TBD | TBD | TBD |

Reproduction (to be completed with the parity runs):
- **Original side:** run the same agent outside Harbor to produce `system_summaries.json`, then grade it with the official grader at commit `8b71342`: `uv run frontier-finance-grader --config eval.example.yaml`. Compare `macro_avg_qualification_rate_on_all_queries`.
- **Harbor side:** `harbor run -c src/frontier-finance/run_frontier-finance.yaml -a <agent> -m "<model>"`. The job mean of `reward` is the same macro qualification rate, provided every trial produced a reward; report excluded trials separately.

## Notes & Caveats

- **Oracle solutions are constructed.** FrontierFinance ships rubrics but no reference answers. Following the adapter guide ("Benchmarks without oracle solutions"), the adapter builds a reference report from each query's rubrics: each rubric is restated as a finding, and negative constraints ("Does not ...") are omitted because they are satisfied by omission. Because LLM judging is not deterministic, the verifier returns reward 1.0 without calling the judges when `/app/report.md` is byte-identical to the task's oracle report (the same approach as the Harbor GDPval adapter, [harbor-framework/harbor#1384](https://github.com/harbor-framework/harbor/pull/1384)). Any other report goes through the judge panel. CL-bench ([harbor-framework/harbor#728](https://github.com/harbor-framework/harbor/pull/728)) likewise skips its judge for the oracle. The oracle run therefore validates task generation, the environment, and the reward plumbing, but not the judge path.
- **Judge-path check.** `judge_calibration.py` regrades a recorded oracle job through the real judge panel with `FF_ORACLE_SHORTCUT=0`, in two conditions: each task's own oracle report (positive control) and another task's oracle report (negative control, reports rotated by one). The judges work if the positive control scores high and the negative control scores near 0. The constructed reports are bullet lists, so the 131 "Format & Presentation" rubrics (for example "presents the data in a table") are not expected to pass, and the positive control is not expected to reach 1.0. Results on a fixed 20-task subset (`random.Random(0)`, 840 rubrics, 114 judge calls per condition): pending judge API keys.

  ```bash
  # from the adapters repo root; the oracle job itself makes no judge calls
  harbor run -p datasets/frontier-finance -a oracle --job-name calib-oracle-20 -i <task> ...
  uv run src/frontier-finance/judge_calibration.py swap jobs/calib-oracle-20 jobs/calib-oracle-20-swapped
  harbor job regrade jobs/calib-oracle-20 -p datasets/frontier-finance --ve FF_ORACLE_SHORTCUT=0 --job-name calib-pos
  harbor job regrade jobs/calib-oracle-20-swapped -p datasets/frontier-finance --ve FF_ORACLE_SHORTCUT=0 --job-name calib-neg
  uv run src/frontier-finance/judge_calibration.py summary jobs/calib-pos jobs/calib-neg
  ```
- **Judge errors.** Upstream excludes a query from every metric when all judges fail on it (`judge_error`). In Harbor, the verifier then writes no reward and exits non-zero, so the trial is recorded as a verifier error rather than as a score. A partial judge failure is handled as upstream: the query is graded on the surviving votes. With two surviving judges a tie goes to the first judge in the panel, as upstream. `grading.json` records `judges_voted` and `failed_checks_by_judge`, and the verifier log prints a warning, so parity reports can count queries graded by fewer than three judges.
- **Missing report.** A missing or empty `/app/report.md` (or a non-file at that path) corresponds to upstream `no_response` and receives reward 0, matching the `..._on_all_queries` metrics.
- **Trials without a reward.** Harbor's job mean averages only trials that produced a reward. Trials that end in a verifier timeout, an all-judges error, or an agent-side infrastructure error are left out, whereas upstream counts a missing response as 0. The Harbor mean equals the upstream macro metric only when every trial produced a reward, so parity reports list excluded trials.
- **Prompt adaptation.** Upstream does not define a system prompt for the system under test. The Harbor instruction gives the query, tells the agent to treat `query_date` as "today", and asks for a self-contained Markdown report at `/app/report.md`. The same instruction text will be used on the original side of parity.
- **Cost and time.** Grading calls three judge models in batches of 30 rubrics, so one task can need up to 48 judge calls (475 rubrics). The adapter sets each task's verifier timeout from its rubric count: 360 s per sequential judge call (upstream's 120 s request timeout times three attempts, since `max_retries=2`) plus 600 s, with a 1800 s floor; the largest task gets 17880 s. JSON-parse retries are not budgeted; actual grading time has not been measured yet.
- **Time-sensitive data.** Queries are anchored to dates from 2024 to 2026. Agents with live web access may see information published after `query_date`, so scores can be optimistic relative to an agent restricted to information available on that date. Both sides of parity share this condition.
- **Rubrics and grader are out of the agent's reach.** The verifier runs in its own container, and `tests/` (rubrics and oracle copy) is only present there.
- **Data terms.** The dataset is gated with a "no resharing outside a gated or private repository" condition. Generated tasks contain the rubrics, so where the dataset is published must respect these terms (to be confirmed with the Harbor team; see the PR discussion).

## Installation / Prerequisites

- Docker installed and running.
- Harbor CLI: `uv tool install harbor`.
- Adapter dependencies:
  ```bash
  cd src/frontier-finance
  uv sync
  ```
- Hugging Face access to the gated dataset (accept the terms, then `hf auth login` or `HF_TOKEN`).
- Judge API keys for the verifier: `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY`.
- Optional: `ANTHROPIC_BASE_URL`, `OPENAI_BASE_URL`, `GOOGLE_GEMINI_BASE_URL` route the judges through a proxy (unset or empty means the provider default).
- Optional: `FF_ORACLE_SHORTCUT=0` sends the oracle report through the judges instead of returning 1.0 (see the judge-path check). Like `FF_JUDGE_MODELS`, it reaches the verifier only via `--ve`.
- Optional: `FF_JUDGE_MODELS` (comma-separated) overrides the judge panel for debugging. It reaches the verifier only via `harbor run --ve FF_JUDGE_MODELS=...`. Use the default panel for reported results.

## Troubleshooting

- **`401` / `GatedRepoError` when generating tasks:** accept the dataset terms on Hugging Face and log in, or pass `--data-path`.
- **Harbor reports missing environment variables:** export the three judge API keys or pass `--env-file`. For oracle-only runs, placeholder values work. Use placeholders longer than a few characters: Harbor redacts secret values from collected artifacts, so a key like `x` rewrites every `x` in `report.md` and breaks the oracle shortcut on regrade.
- **Verifier error with "All judges failed":** check the API keys and provider status; the trial can be retried with `harbor job resume`.
- **Verifier timeout on very large rubric sets:** increase `--verifier-timeout-multiplier` (or the `[verifier].timeout_sec` value).

## Citation

```bibtex
@article{zhang2026frontierfinance,
  title   = {FrontierFinance: A Challenging Benchmark for Measuring Frontier Intelligence of Finance Agents},
  author  = {Zhang, Yuhao and Koyluoglu, O. Ozan and Venkatesh, Thejas and Diehl Martinez, Richard and Bhatia, Vishank and Alidoust, Arash and Paranjape, Ashwin},
  year    = {2026},
  url     = {https://samaya.ai/blog/frontier-finance}
}
```

## Authors & Contributions

This adapter is developed and maintained by [Chaoqi](https://github.com/Chaoqi31).

**Issues and Contributions:**
- Submit issues and pull requests to [harbor-index/adapters](https://github.com/harbor-index/adapters).

## Acknowledgement

API inference compute for running parity tests is generously supported by [2077AI](https://www.2077ai.com/) (https://www.2077ai.com/).

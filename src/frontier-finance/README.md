## FrontierFinance → Harbor Adapter

## Overview

FrontierFinance evaluates finance AI agents on open-ended, long-form research questions asked by investment professionals: company research, earnings and events, financial data and modeling, sector/industry/macro analysis, coverage and catalyst monitoring, and screening and discovery. Answers are free-form English reports graded against expert-authored rubrics by an LLM judge panel.

- **Size:** 220 queries with 11,543 rubrics (3 to 475 rubrics per query, median 27; 65% marked `must_have`). This adapter converts **all 220 queries into 220 Harbor tasks** (one task per query). No queries are excluded.
- **Provenance:** [samaya-ai/FrontierFinance](https://huggingface.co/datasets/samaya-ai/FrontierFinance) (Hugging Face dataset, revision `36afd6dc1cbb2c4512536daf917dc28b1225a720`) and the official grader [samaya-ai/frontier-finance](https://github.com/samaya-ai/frontier-finance) (commit `8b71342dc7730eb1803dd3934e17bc71c9922ec5`), installed from the parity fork's commit [`e287476`](https://github.com/Chaoqi31/frontier-finance/commit/e28747624053c3caca98489db9144c7c9372b34c), which adds one judge-compatibility change.
- **License:** dataset CC-BY-4.0, grader Apache-2.0. The dataset is gated on Hugging Face; its terms ask users not to reshare it outside a gated or private repository.
- **Main adaptation:** the original benchmark only grades responses produced by an external system. Here, the query becomes an agent instruction, the agent writes its report to `/app/report.md`, and the verifier runs the upstream grader on that report (upstream `8b71342` plus one judge-compatibility change, see Adapter Features).

## What is FrontierFinance?

FrontierFinance ([blog](https://samaya.ai/blog/frontier-finance), [website](https://research.samaya.ai/benchmarks/frontier-finance), [arXiv](https://arxiv.org/abs/2608.11683)) is a benchmark from Samaya AI for measuring the frontier intelligence of finance agents. Each of its 220 expert-crafted queries comes with a date (`query_date`, the temporal anchor for the question) and a set of atomic, verifiable rubrics that a good answer should satisfy. A panel of three judges (Claude Sonnet 4.6, Gemini 3.1 Pro, GPT-5.4) labels each rubric as satisfied or not, and a rubric counts as qualified by majority vote. The headline metric is the **rubric qualification rate**, reported both as a macro average (mean of per-query rates) and a micro average (total qualified / total rubrics), for all rubrics and for the `must_have` subset.

## Adapter Features

- **Data loading:** downloads `frontier_finance_public.jsonl` from Hugging Face at a pinned revision (requires accepting the dataset terms and `hf auth login` / `HF_TOKEN`), or reads a local copy via `--data-path`.
- **Stable task IDs:** `frontier-finance-<query_id>`, using the upstream 16-hex `query_id`; task names are `samaya-ai/frontier-finance__<query_id>`.
- **Upstream grading:** the Docker image installs the `frontier-finance` grader at a pinned commit in an isolated virtualenv (`/opt/ff-grader`), using upstream's `uv.lock` so the judge SDK versions (anthropic 0.116.0, google-genai 2.10.0, openai 2.44.0) match upstream. `tests/grade.py` builds the upstream `EvalItem` from the task's rubrics and the agent's report and calls the upstream `Grader` with the judge panel and settings from upstream `eval.example.yaml` (`max_rubrics_per_call=30`, `max_tokens=32000`, `request_timeout=120`, `max_retries=2`, `max_json_parse_retries=1`). Prompts, batching, parsing, and majority voting are the upstream code. The pinned commit is upstream `8b71342` plus one change in `judges.py`, so that newer judge models accept the grader's requests: no `temperature` for Claude Haiku 5+ and GPT-6+, and `LOW` thinking when a Gemini 3 Flash model rejects `MINIMAL`. Requests to the default panel are unchanged.
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
├── run_frontier-finance_parity.yaml   # Harbor side of parity: claude-code on Daytona
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
uv run frontier-finance --split parity --output-dir ../../datasets/frontier-finance-parity  # parity subset
```

Available flags:
- `--output-dir`: where to write tasks (default `datasets/frontier-finance` at the repo root)
- `--limit`: generate only the first N tasks (sorted by `query_id`)
- `--overwrite`: overwrite existing task directories
- `--task-ids`: only generate these tasks (upstream `query_id` or local task id)
- `--data-path`: use a local `frontier_finance_public.jsonl` instead of downloading
- `--split`: `full` (default, all 220 tasks) or `parity` (the 11-task parity subset)

## Comparison with Original Benchmark (Parity)

Parity matches: the run-score ranges of the two sides overlap (table below). Upstream ships a grader but no agent harness, so this is Scenario 2 of the adapter guide: a fork of the original benchmark adds a runner for a standard Harbor agent, and the same agent runs on both sides. The agent is `claude-code`, as in DeepSynth, Seal-0 and WideSearch, pinned to version 2.1.330 on both sides, with `claude-haiku-5-5` through the parity gateway. Each side runs the parity subset three times.

**Model and judges.** Parity checks the adaptation, not model ability, so it uses cheap models, as agreed with the Harbor team. The judges are current cheap models from the three upstream judge vendors, in upstream's order: `claude-haiku-5-5`, `gemini-3.8-flash`, `gpt-6-luna` (`FF_JUDGE_MODELS` in `run_frontier-finance_parity.yaml`, `judge_models` in the fork's `harbor_parity/eval.parity.yaml`). The same panel grades both sides, so parity holds; the scores are not comparable with the upstream leaderboard, which uses the full panel. The Claude judge and the agent model share a vendor; any self-preference applies equally to both sides, so it does not affect the parity comparison. The task default stays the upstream panel. The grader carries one compatibility change in `frontier_finance/judges.py` for these newer judges, which the pinned upstream commit predates: no `temperature` for Claude Haiku 5+ and GPT-6+, which reject it, and `LOW` thinking when a Gemini 3 Flash model rejects `MINIMAL`. Prompts, batching, parsing and voting are unchanged, and the upstream panel is sent the same requests as before. Both sides install the grader from the same fork commit.

**Parity subset.** As agreed with the Harbor team, parity runs on 5% of the benchmark: 11 of the 220 queries (`--split parity`). Parity checks that the adaptation is faithful, not model ability, so a small representative subset is enough. Each query has exactly one use case, so the subset is stratified by use case: the 11 slots are allocated in proportion to each use case's share by largest remainder (financial data and modeling 3; company research, earnings and events, sector and macro 2 each; coverage and catalyst monitoring, screening and discovery 1 each), and the queries are drawn with `random.Random(0)` (`parity_subset` in `adapter.py`). The subset has 424 rubrics (6 to 84 per query) and spans query dates from 2024-08 to 2026-04. Its query IDs: `0de600d0386ab53c`, `7dc0e678415f1fd4`, `8d7ee1f40b5244a7`, `9488d3698bafd842`, `a7606d2a0a4bea29`, `bc435f09355f23bc`, `c1d3968daefa7a8e`, `e10acfd0ef14a72c`, `e74672d9b526d701`, `f84db8e5d5d58f43`, `f89b633e396a1d7d`.

| Agent | Model | Metric | Number of Runs | Dataset Size | Original Benchmark Performance | Harbor Adapter Performance |
|-------|-------|--------|------------------|--------------|------------------------------|----------------------------|
| claude-code@2.1.330 | claude-haiku-5-5 | Macro rubric qualification rate | 3 | 11 tasks (5% of 220) | 0.3540 ± 0.0405 | 0.3448 ± 0.0326 |

Scores are mean ± sample SEM over runs, as fractions. Original runs: 0.3868, 0.4017, 0.2734 (range 0.273 to 0.402). Harbor runs: 0.4064, 0.2957, 0.3324 (range 0.296 to 0.406). The ranges overlap. The gap between the means (0.009) is far smaller than the spread between runs on either side.

All 66 agent runs (11 queries × 3 runs × 2 sides) ended with claude-code status `success` and a report, so no run was rerun, and all three judges voted on every query, so no query was regraded. Per-query disagreements change direction across runs (for example, `7dc0e678` scored higher on Harbor in run 1 and higher on the original side in runs 2 and 3), which points to sampling noise rather than a systematic difference. Both sides ran on Daytona, 8 at a time, through the same gateway. The whole parity experiment, including the sanity run and the judge-path check, cost about $8 on the gateway's billing, of which claude-code reports $6.23 for the 66 agent runs.

Both sides run the same `claude-code` version and model with Harbor's flags (`--verbose --output-format=stream-json --permission-mode=bypassPermissions --print`) and environment variables, including the model aliases Harbor sets for a custom base URL. Host variables that Harbor reads into claude-code's flags or environment (`CLAUDE_CODE_MAX_TURNS`, `CLAUDE_CODE_EFFORT_LEVEL`, `MAX_THINKING_TOKENS`, `CLAUDE_CODE_MAX_OUTPUT_TOKENS`, `CLAUDE_CODE_DISABLE_ADAPTIVE_THINKING`, the alias variables) stay unset on both sides; the original-side runner refuses to start if any is set. Both use the same `instruction.md` on stdin, the same 3600 s agent limit and resources from `task.toml`, and the same concurrency. The original side runs each query in a fresh container built from the task's own `environment/Dockerfile` plus Harbor's claude-code install step, and `/app/report.md` becomes the query's `system_summary` for the upstream grader.

- Original parity repository: [Chaoqi31/frontier-finance, branch `harbor-parity`](https://github.com/Chaoqi31/frontier-finance/tree/harbor-parity/harbor_parity), a fork of [samaya-ai/frontier-finance](https://github.com/samaya-ai/frontier-finance) @ `8b71342` that adds `harbor_parity/` and the judge-compatibility change in `frontier_finance/judges.py`

Reproduction (keys come from the environment):

```bash
# Original side, from the fork's root: run claude-code outside Harbor, then grade with the upstream CLI
python harbor_parity/run_claude_code.py run -d <adapters>/datasets/frontier-finance-parity -o runs/original1 \
    -m claude-haiku-5-5 --claude-code-version 2.1.330 -n 8 --backend daytona
python harbor_parity/run_claude_code.py collect runs/original1 --summaries runs/original1/system_summaries.json
cat <adapters>/datasets/frontier-finance-parity/*/tests/rubrics.jsonl > parity_rubrics.jsonl   # the rubrics of the queries that ran
uv run --frozen --extra all frontier-finance-grader --config harbor_parity/eval.parity.yaml \
    --responses runs/original1/system_summaries.json --output-dir runs/original1/grades
python harbor_parity/run_claude_code.py score runs/original1/grades/per_item.json [<regrade>/per_item.json ...]

# Harbor side, from the adapters repository root, after generating datasets/frontier-finance-parity
harbor run -y -c src/frontier-finance/run_frontier-finance_parity.yaml --env-file <keys.env>
python <fork>/harbor_parity/run_claude_code.py collect jobs/<job> [jobs/<rerun job> ...]
```

One rerun rule applies to both sides. `collect` reads each run's status from the final `result` event of claude-code's stream log, the same file on both sides. `success`, `error_max_turns` and `timeout` are results and are scored, 0 without a report. Any other status (an API error, `error_during_execution`, no `result` event) is an infrastructure failure and is rerun: on the original side by repeating the same `run` command, on the Harbor side by a new job over the listed tasks (`collect` prints the `-i` filters; pass them with `-p datasets/frontier-finance-parity`), passed to `collect` after the first job. Harbor's own retry stays off (`max_retries` 0, the default), so Harbor's error policy does not rerun or drop trials differently from the original side. `collect` reports the rerun count and, for a Harbor run, the mean reward over trials with a final status, which is the number compared with upstream `macro_avg_qualification_rate_on_all_queries`. `collect --summaries` on a Harbor job exports its reports for a cross-grade with the upstream CLI.

Grading follows one rule too. A query whose grading lost any judge's votes (`judge_error`, or a non-empty `failed_checks_by_judge`) is regraded on its own: `score` lists these on the original side, and `collect` lists them on the Harbor side (from each trial's `grading.json`) and leaves them out of the mean until `harbor job regrade` replaces them. Parity reports the number of regraded queries per side.

## Notes & Caveats

- **Oracle solutions are constructed.** FrontierFinance ships rubrics but no reference answers. Following the adapter guide ("Benchmarks without oracle solutions"), the adapter builds a reference report from each query's rubrics: each rubric is restated as a finding, and negative constraints ("Does not ...") are omitted because they are satisfied by omission. Because LLM judging is not deterministic, the verifier returns reward 1.0 without calling the judges when `/app/report.md` is byte-identical to the task's oracle report (the same approach as the Harbor GDPval adapter, [harbor-framework/harbor#1384](https://github.com/harbor-framework/harbor/pull/1384)). Any other report goes through the judge panel. CL-bench ([harbor-framework/harbor#728](https://github.com/harbor-framework/harbor/pull/728)) likewise skips its judge for the oracle. The oracle run therefore validates task generation, the environment, and the reward plumbing, but not the judge path.
- **Judge-path check.** `judge_calibration.py` regrades a recorded oracle job through the real judge panel with `FF_ORACLE_SHORTCUT=0`, in two conditions: each task's own oracle report (positive control) and another task's oracle report (negative control, reports rotated by one). The judges work if the positive control scores high and the negative control scores near 0. The constructed reports are bullet lists, so the 131 "Format & Presentation" rubrics (for example "presents the data in a table") are not expected to pass, and the positive control is not expected to reach 1.0. With the parity judge panel (`claude-haiku-5-5`, `gemini-3.8-flash`, `gpt-6-luna`) on the 5 parity tasks with the fewest rubrics (`0de600d0386ab53c`, `8d7ee1f40b5244a7`, `a7606d2a0a4bea29`, `e74672d9b526d701`, `f84db8e5d5d58f43`; 74 rubrics, 15 judge calls per condition), all three judges voted on every task: the positive control scored 0.976 ± 0.016 (SEM; 3 tasks at 1.0, the others 0.955 and 0.923) and the negative control 0.011 ± 0.011 (4 tasks at 0, one at 0.053). The upstream panel has not been calibrated here.

  ```bash
  # from the adapters repo root; the oracle job itself makes no judge calls
  harbor run -p datasets/frontier-finance -a oracle --job-name calib-oracle-20 -i <task> ...
  uv run src/frontier-finance/judge_calibration.py swap jobs/calib-oracle-20 jobs/calib-oracle-20-swapped
  harbor job regrade jobs/calib-oracle-20 -p datasets/frontier-finance --ve FF_ORACLE_SHORTCUT=0 --job-name calib-pos
  harbor job regrade jobs/calib-oracle-20-swapped -p datasets/frontier-finance --ve FF_ORACLE_SHORTCUT=0 --job-name calib-neg
  uv run src/frontier-finance/judge_calibration.py summary jobs/calib-pos jobs/calib-neg
  ```
  For the parity panel, add `--ve FF_JUDGE_MODELS=claude-haiku-5-5,gemini-3.8-flash,gpt-6-luna` to both regrades.
- **Judge errors.** Upstream excludes a query from every metric when all judges fail on it (`judge_error`). In Harbor, the verifier then writes no reward and exits non-zero, so the trial is recorded as a verifier error rather than as a score. A partial judge failure is handled as upstream: the query is graded on the surviving votes. With two surviving judges a tie goes to the first judge in the panel, as upstream. `grading.json` records `judges_voted` and `failed_checks_by_judge`, and the verifier log prints a warning, so parity reports can count queries graded by fewer than three judges.
- **Missing report.** A missing or empty `/app/report.md` (or a non-file at that path) corresponds to upstream `no_response` and receives reward 0, matching the `..._on_all_queries` metrics.
- **Trials without a valid reward.** Harbor's job mean leaves out trials without a reward and trials whose recorded exception marks the reward invalid under Harbor's error policy (for example an API error), whereas upstream counts a missing response as 0. Parity therefore compares the mean reported by `collect`, which applies the rerun rule above to both sides, rather than Harbor's job mean.
- **Prompt adaptation.** Upstream does not define a system prompt for the system under test. The Harbor instruction gives the query, tells the agent to treat `query_date` as "today", and asks for a self-contained Markdown report at `/app/report.md`. Both parity sides pass this instruction unchanged.
- **Cost and time.** Grading calls three judge models in batches of 30 rubrics, so one task can need up to 48 judge calls (475 rubrics). The adapter sets each task's verifier timeout from its rubric count: 360 s per sequential judge call (upstream's 120 s request timeout times three attempts, since `max_retries=2`) plus 600 s, with a 1800 s floor; the largest task gets 17880 s. JSON-parse retries are not budgeted; actual grading time has not been measured yet.
- **Time-sensitive data.** Queries are anchored to dates from 2024 to 2026. Agents with live web access may see information published after `query_date`, so scores can be optimistic relative to an agent restricted to information available on that date. Both sides of parity share this condition.
- **Rubrics and grader are out of the agent's reach.** The verifier runs in its own container, and `tests/` (rubrics and oracle copy) is only present there.
- **Data terms.** The dataset is gated with a "no resharing outside a gated or private repository" condition. Generated tasks contain the rubrics. Like other gated sources already in `harbor-datasets` with their answers (GPQA-diamond, HLE, GAIA, DeepSynth), the tasks are published there with the terms stated here. Generating the tasks requires accepting the terms on Hugging Face. Do not reshare the rubrics or oracle reports outside Harbor.

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
- Optional: `ANTHROPIC_BASE_URL`, `OPENAI_BASE_URL`, `GOOGLE_GEMINI_BASE_URL` route the judges through a proxy (unset or empty means the provider default). For the parity gateway they are `https://app.ppapi.ai`, `https://app.ppapi.ai/v1` and `https://app.ppapi.ai`.
- Optional: `FF_ORACLE_SHORTCUT=0` sends the oracle report through the judges instead of returning 1.0 (see the judge-path check). Like `FF_JUDGE_MODELS`, it reaches the verifier only via `--ve`.
- Optional: `FF_JUDGE_MODELS` (comma-separated) overrides the judge panel. It reaches the verifier via `harbor run --ve FF_JUDGE_MODELS=...` or a job config's `verifier.env`; `run_frontier-finance_parity.yaml` sets the parity panel this way.

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

"""CLI entry point: generate FrontierFinance Harbor tasks."""

import argparse
from pathlib import Path

from .adapter import FrontierFinanceAdapter

# Default output dir: <repo>/datasets/<adapter_id>
DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parents[4] / "datasets" / "frontier-finance"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory to write generated tasks",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Generate only the first N tasks",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing tasks",
    )
    parser.add_argument(
        "--task-ids",
        nargs="+",
        default=None,
        help="Only generate these task IDs (upstream query_id or local task id)",
    )
    parser.add_argument(
        "--data-path",
        type=Path,
        default=None,
        help="Local frontier_finance_public.jsonl (default: download from Hugging Face)",
    )
    args = parser.parse_args()

    adapter = FrontierFinanceAdapter(
        args.output_dir,
        overwrite=args.overwrite,
        limit=args.limit,
        task_ids=args.task_ids,
        data_path=args.data_path,
    )

    adapter.run()


if __name__ == "__main__":
    main()

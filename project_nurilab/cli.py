"""Command-line interface for Python static review analysis."""

from __future__ import annotations

import argparse
from pathlib import Path

from project_nurilab.config import DEFAULT_REPORT_DIR
from project_nurilab.llm.review import LocalLLMReviewClient, MockReviewClient
from project_nurilab.pipeline import Phase1Pipeline


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser."""

    parser = argparse.ArgumentParser(
        prog="project-nurilab",
        description="Python code review and static security analysis.",
    )
    subparsers = parser.add_subparsers(dest="command")

    analyze = subparsers.add_parser(
        "analyze",
        help="Analyze one Python file or project directory and generate reports.",
    )
    analyze.add_argument("path", help="Path to a .py file or project directory.")
    analyze.add_argument(
        "--out",
        default=DEFAULT_REPORT_DIR,
        help=f"Output directory for reports. Defaults to {DEFAULT_REPORT_DIR}.",
    )
    analyze.add_argument(
        "--max-lines",
        type=int,
        default=None,
        help="Deprecated and ignored; Python files are no longer skipped by line count.",
    )
    analyze.add_argument(
        "--format",
        nargs="+",
        choices=["html", "json", "md"],
        default=None,
        metavar="FORMAT",
        help=(
            "Report output formats in any order. Supported: html json md. "
            "Defaults to html json."
        ),
    )
    analyze.add_argument(
        "--review-client",
        choices=["mock", "local"],
        default="mock",
        help=(
            "Review backend. 'mock' is deterministic and offline; 'local' calls "
            "a vLLM OpenAI-compatible server."
        ),
    )
    analyze.add_argument(
        "--no-ruff",
        action="store_true",
        help="Disable Ruff JSON result collection.",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the CLI and return a process exit code."""

    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command != "analyze":
        parser.print_help()
        return 0

    review_client = (
        LocalLLMReviewClient() if args.review_client == "local" else MockReviewClient()
    )
    pipeline = Phase1Pipeline(
        review_client=review_client,
        use_ruff=not args.no_ruff,
    )
    report, output_paths = pipeline.run(
        input_path=Path(args.path),
        output_dir=Path(args.out),
        formats=args.format,
    )

    target_path = getattr(report.analysis, "path", None) or getattr(
        report.analysis,
        "root_path",
        "",
    )
    print(f"Analyzed: {target_path}")
    print(f"Risk Level: {report.review.risk_level}")
    for output_format, output_path in output_paths.items():
        print(f"{output_format.upper()} Report: {output_path}")
    return 0

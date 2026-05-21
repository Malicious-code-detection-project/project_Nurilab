"""Command-line interface for the phase 1 MVP."""

from __future__ import annotations

import argparse
from pathlib import Path

from project_nurilab.config import DEFAULT_MAX_LINES, DEFAULT_REPORT_DIR
from project_nurilab.input.manager import PythonFileLoader
from project_nurilab.pipeline import Phase1Pipeline


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser."""

    parser = argparse.ArgumentParser(
        prog="project-nurilab",
        description="Phase 1 Python code review and security review MVP.",
    )
    subparsers = parser.add_subparsers(dest="command")

    analyze = subparsers.add_parser(
        "analyze",
        help="Analyze one Python file and generate Markdown/JSON reports.",
    )
    analyze.add_argument("path", help="Path to a .py file with 200 lines or fewer.")
    analyze.add_argument(
        "--out",
        default=DEFAULT_REPORT_DIR,
        help=f"Output directory for reports. Defaults to {DEFAULT_REPORT_DIR}.",
    )
    analyze.add_argument(
        "--max-lines",
        type=int,
        default=DEFAULT_MAX_LINES,
        help=f"Maximum allowed source lines. Defaults to {DEFAULT_MAX_LINES}.",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the CLI and return a process exit code."""

    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command != "analyze":
        parser.print_help()
        return 0

    pipeline = Phase1Pipeline(loader=PythonFileLoader(max_lines=args.max_lines))
    report, markdown_path, json_path = pipeline.run(
        input_path=Path(args.path),
        output_dir=Path(args.out),
    )

    print(f"Analyzed: {report.analysis.path}")
    print(f"Risk Level: {report.review.risk_level}")
    print(f"Markdown Report: {markdown_path}")
    print(f"JSON Report: {json_path}")
    return 0

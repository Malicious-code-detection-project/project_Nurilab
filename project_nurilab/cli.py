"""Command-line interface for Python static review analysis."""

from __future__ import annotations

import argparse
from pathlib import Path

from project_nurilab.config import DEFAULT_REPORT_DIR
from project_nurilab.external.jadx_mcp_client import JadxMcpClient
from project_nurilab.llm.review import LocalLLMReviewClient, MockReviewClient
from project_nurilab.pipeline import Phase1Pipeline
from project_nurilab.schemas import ExternalToolCall


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
    analyze.add_argument(
        "--jadx-mcp-class",
        default=None,
        metavar="CLASS",
        help=(
            "Opt in to one jadx-ai-mcp get_class_source call for this fully "
            "qualified class. Requires an already-running jadx-mcp-server."
        ),
    )
    analyze.add_argument(
        "--jadx-mcp-url",
        default=None,
        metavar="URL",
        help=(
            "jadx-mcp-server endpoint. Defaults to NURILAB_JADX_MCP_URL or "
            "http://127.0.0.1:8651/mcp. Requires --jadx-mcp-class."
        ),
    )
    analyze.add_argument(
        "--jadx-mcp-target",
        default=None,
        metavar="NAME",
        help=(
            "Identifier of the APK loaded in JADX-GUI, recorded as-is and not "
            "verified. Requires --jadx-mcp-class."
        ),
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the CLI and return a process exit code."""

    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command != "analyze":
        parser.print_help()
        return 0
    if args.jadx_mcp_class is None and (args.jadx_mcp_url or args.jadx_mcp_target):
        parser.error("--jadx-mcp-url and --jadx-mcp-target require --jadx-mcp-class")

    review_client = (
        LocalLLMReviewClient() if args.review_client == "local" else MockReviewClient()
    )
    jadx_mcp_client = (
        JadxMcpClient(url=args.jadx_mcp_url) if args.jadx_mcp_class else None
    )
    pipeline = Phase1Pipeline(
        review_client=review_client,
        use_ruff=not args.no_ruff,
        jadx_mcp_client=jadx_mcp_client,
    )
    report, output_paths = pipeline.run(
        input_path=Path(args.path),
        output_dir=Path(args.out),
        formats=args.format,
        jadx_mcp_class=args.jadx_mcp_class,
        jadx_mcp_target=args.jadx_mcp_target,
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
    for call in report.external_tool_calls:
        print(_format_external_tool_call(call))
    return 0


def _format_external_tool_call(call: ExternalToolCall) -> str:
    """One status line per MCP call; reports show it once THE-155 lands."""

    prefix = f"JADX MCP {call.tool}: {call.status}"
    if call.status == "success":
        truncated = ", truncated" if call.truncated else ""
        return f"{prefix} ({call.response_size_bytes:,} bytes{truncated})"
    reason = (call.reason or "").strip().splitlines()
    return f"{prefix} - {reason[0]}" if reason else prefix

"""Command line entry point for sysopt-cachekey."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from .rules import SEVERITIES, SEVERITY_RANK, Report, analyze
from .workflow import WorkflowError, extract_cache_steps, load_workflow


def discover(paths: Sequence[str]) -> list[Path]:
    found: list[Path] = []
    for raw in paths or [".github/workflows"]:
        path = Path(raw)
        if path.is_dir():
            found.extend(sorted(path.rglob("*.yml")))
            found.extend(sorted(path.rglob("*.yaml")))
        elif path.is_file():
            found.append(path)
    seen: set[Path] = set()
    unique: list[Path] = []
    for path in found:
        resolved = path.resolve()
        if resolved not in seen:
            seen.add(resolved)
            unique.append(path)
    return unique


def scan(paths: Sequence[str]) -> tuple[Report, list[str]]:
    files = discover(paths)
    all_steps = []
    workflow_count = 0
    errors: list[str] = []
    for path in files:
        try:
            document = load_workflow(path)
            steps = extract_cache_steps(str(path), document)
        except WorkflowError as exc:
            errors.append(str(exc))
            continue
        workflow_count += 1
        all_steps.extend(steps)
    return analyze(all_steps, workflows=workflow_count), errors


def _render_text(report: Report, shown: list) -> str:
    lines: list[str] = []
    current: str | None = None
    for finding in shown:
        if finding.workflow != current:
            current = finding.workflow
            lines.append(f"{current}")
        lines.append(f"  {finding.job}:{finding.step}  {finding.severity:<7} {finding.rule}")
        lines.append(f"      {finding.message}")
        lines.append(f"      -> {finding.suggestion}")
    counts = report.counts()
    lines.append("")
    lines.append(
        f"{len(report.findings)} finding(s): "
        f"{counts['error']} error, {counts['warning']} warning, {counts['info']} info "
        f"across {report.workflows} workflow(s), {report.cache_steps} cache step(s)"
    )
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sysopt-cachekey",
        description="Find GitHub Actions cache keys that cannot hit, collide, or go stale.",
    )
    parser.add_argument(
        "paths",
        nargs="*",
        help="workflow files or directories (default: .github/workflows)",
    )
    parser.add_argument(
        "--format", choices=("text", "json"), default="text", help="output format"
    )
    parser.add_argument(
        "--min-severity",
        choices=SEVERITIES,
        default="info",
        help="only show findings at or above this severity (default: info)",
    )
    parser.add_argument(
        "--fail-on",
        choices=("none", *SEVERITIES),
        default="warning",
        help="exit 1 when a finding at or above this severity exists (default: warning)",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report, errors = scan(args.paths)
    for error in errors:
        print(f"warning: {error}", file=sys.stderr)

    shown = report.at_least(args.min_severity)
    if args.format == "json":
        payload = {
            "workflows": report.workflows,
            "cache_steps": report.cache_steps,
            "counts": report.counts(),
            "findings": [f.to_dict() for f in shown],
            "errors": errors,
        }
        print(json.dumps(payload, indent=2))
    else:
        print(_render_text(report, shown))

    if report.workflows == 0:
        return 2
    if args.fail_on != "none" and any(
        SEVERITY_RANK[f.severity] >= SEVERITY_RANK[args.fail_on] for f in report.findings
    ):
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
"""Cache-key rules and findings."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from .workflow import CacheStep

SEVERITIES = ("info", "warning", "error")
SEVERITY_RANK = {name: rank for rank, name in enumerate(SEVERITIES)}

VOLATILE_TOKENS = (
    "github.run_id",
    "github.run_number",
    "github.run_attempt",
    "github.sha",
    "strategy.job-index",
)

DEPENDENCY_MARKERS = {
    "node_modules": "node",
    "package-lock": "node",
    ".cache/pip": "python",
    "site-packages": "python",
    ".venv": "python",
    "pip": "python",
    ".cargo": "rust",
    "go/pkg/mod": "go",
    ".m2": "java",
    ".gradle": "java",
    "vendor/bundle": "ruby",
}

LOCKFILE_HINTS = {
    "node": "hashFiles('**/package-lock.json', '**/yarn.lock', '**/pnpm-lock.yaml')",
    "python": "hashFiles('**/poetry.lock', '**/requirements*.txt', '**/uv.lock')",
    "rust": "hashFiles('**/Cargo.lock')",
    "go": "hashFiles('**/go.sum')",
    "java": "hashFiles('**/pom.xml', '**/build.gradle*')",
    "ruby": "hashFiles('**/Gemfile.lock')",
    "generic": "hashFiles('**/lockfile')",
}

BROAD_PATHS = {"", "/", "~", ".", "./", "${{ github.workspace }}"}


@dataclass(frozen=True)
class Finding:
    """One actionable cache-key problem."""

    rule: str
    severity: str
    workflow: str
    job: str
    step: int
    message: str
    suggestion: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule": self.rule,
            "severity": self.severity,
            "workflow": self.workflow,
            "job": self.job,
            "step": self.step,
            "message": self.message,
            "suggestion": self.suggestion,
        }


@dataclass
class Report:
    findings: list[Finding] = field(default_factory=list)
    workflows: int = 0
    cache_steps: int = 0

    def at_least(self, severity: str) -> list[Finding]:
        limit = SEVERITY_RANK[severity]
        return [f for f in self.findings if SEVERITY_RANK[f.severity] >= limit]

    def counts(self) -> dict[str, int]:
        counts = dict.fromkeys(SEVERITIES, 0)
        for finding in self.findings:
            counts[finding.severity] += 1
        return counts


def _lockfile_hint(paths: Iterable[str]) -> str:
    kinds: list[str] = []
    for path in paths:
        lowered = path.lower()
        for marker, kind in DEPENDENCY_MARKERS.items():
            if marker in lowered:
                kinds.append(kind)
    for kind in kinds:
        if kind in LOCKFILE_HINTS:
            return LOCKFILE_HINTS[kind]
    return LOCKFILE_HINTS["generic"]


def _check_step(step: CacheStep, duplicate_keys: set[str]) -> list[Finding]:
    findings: list[Finding] = []

    def add(rule: str, severity: str, message: str, suggestion: str) -> None:
        findings.append(
            Finding(
                rule=rule,
                severity=severity,
                workflow=step.workflow,
                job=step.job,
                step=step.index + 1,
                message=message,
                suggestion=suggestion,
            )
        )

    if not step.key:
        add(
            "missing-key",
            "error",
            "cache step has no key, so it can never be restored",
            "set `with.key` to a stable, content-addressed key",
        )
        return findings

    volatile = [token for token in VOLATILE_TOKENS if token in step.key]
    if volatile:
        add(
            "volatile-key",
            "error",
            f"cache key contains {', '.join(volatile)}, which changes on every run",
            "remove the volatile token and hash the dependency files instead",
        )

    if step.multi_os and "runner.os" not in step.key and "matrix.os" not in step.key:
        add(
            "missing-os",
            "warning",
            "workflow runs on multiple operating systems but the key does not include runner.os",
            "prefix the key with `${{ runner.os }}-` to avoid cross-OS cache collisions",
        )

    joined_paths = " ".join(step.paths).lower()
    depends_on_packages = any(marker in joined_paths for marker in DEPENDENCY_MARKERS)
    if depends_on_packages and "hashfiles(" not in step.key.lower():
        add(
            "no-lockfile-hash",
            "warning",
            "dependency cache key does not hash a lockfile, so stale packages can be restored",
            f"include {_lockfile_hint(step.paths)} in the key",
        )

    if not step.paths:
        add(
            "missing-path",
            "error",
            "cache step has no path, so there is nothing to store",
            "set `with.path` to the directory or file to cache",
        )
    for path in step.paths:
        if path.strip() in BROAD_PATHS:
            add(
                "broad-path",
                "warning",
                f"cache path {path!r} is too broad and can capture unrelated files",
                "cache only the dependency directory, e.g. node_modules or ~/.cache/pip",
            )

    if not step.restore_keys:
        add(
            "no-restore-keys",
            "info",
            "cache has no restore-keys, so a near-miss key cannot provide a partial cache",
            "add a broader prefix such as `${{ runner.os }}-pip-`",
        )

    if step.key in duplicate_keys:
        add(
            "duplicate-key",
            "warning",
            "the same cache key is used by multiple steps with different paths",
            "make each key unique to the directory it stores",
        )

    return findings


def analyze(steps: list[CacheStep], workflows: int = 0) -> Report:
    report = Report(workflows=workflows, cache_steps=len(steps))
    key_paths: dict[str, set[tuple[str, ...]]] = {}
    for step in steps:
        if step.key:
            key_paths.setdefault(step.key, set()).add(tuple(sorted(step.paths)))
    duplicate_keys = {key for key, paths in key_paths.items() if len(paths) > 1}

    for step in steps:
        report.findings.extend(_check_step(step, duplicate_keys))
    report.findings.sort(
        key=lambda f: (f.workflow, f.job, f.step, -SEVERITY_RANK[f.severity], f.rule)
    )
    return report
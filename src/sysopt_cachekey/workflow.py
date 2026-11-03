"""Parse GitHub Actions workflows and extract cache steps."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


class WorkflowError(ValueError):
    """Raised when a workflow cannot be parsed."""


@dataclass
class CacheStep:
    """One actions/cache step, with the context needed by the rules."""

    workflow: str
    job: str
    index: int
    uses: str
    key: str | None
    paths: list[str] = field(default_factory=list)
    restore_keys: list[str] = field(default_factory=list)
    runs_on: list[str] = field(default_factory=list)

    @property
    def location(self) -> str:
        return f"{self.workflow}:{self.job}:{self.index}"

    @property
    def multi_os(self) -> bool:
        families = {os_family(value) for value in self.runs_on}
        families.discard("")
        return len(families) > 1


def os_family(value: str) -> str:
    """Map a runs-on label to linux, macos, or windows."""
    lowered = str(value).lower()
    for needle, family in (
        ("ubuntu", "linux"),
        ("linux", "linux"),
        ("macos", "macos"),
        ("mac", "macos"),
        ("windows", "windows"),
        ("win", "windows"),
    ):
        if needle in lowered:
            return family
    return ""


def _normalize(document: Any) -> dict:
    if document is None:
        raise WorkflowError("workflow is empty")
    if not isinstance(document, dict):
        raise WorkflowError("workflow root must be a mapping")
    # PyYAML resolves the unquoted ``on:`` key to True (YAML 1.1 booleans).
    if True in document and "on" not in document:
        document["on"] = document.pop(True)
    return document


def load_workflow(path: str | Path) -> dict:
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise WorkflowError(f"cannot read {path}: {exc}") from exc
    try:
        document = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise WorkflowError(f"invalid YAML in {path}: {exc}") from exc
    return _normalize(document)


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, str):
        return [line.strip() for line in value.splitlines() if line.strip()]
    return [str(value)]


def _runs_on(job: dict) -> list[str]:
    runs_on = job.get("runs-on")
    labels = _as_list(runs_on)
    matrix = (job.get("strategy") or {}).get("matrix") or {}
    if isinstance(matrix, dict):
        for key in ("os", "runner", "platform"):
            labels.extend(_as_list(matrix.get(key)))
    return labels


def is_cache_action(uses: str) -> bool:
    name = uses.split("@", 1)[0].strip().lower()
    return name in {"actions/cache", "actions/cache/save", "actions/cache/restore"}


def extract_cache_steps(workflow: str, document: dict) -> list[CacheStep]:
    """Return every actions/cache step in the workflow."""
    jobs = document.get("jobs")
    if not isinstance(jobs, dict):
        return []

    steps: list[CacheStep] = []
    for job_name, job in jobs.items():
        if not isinstance(job, dict):
            continue
        job_steps = job.get("steps")
        if not isinstance(job_steps, list):
            continue
        runs_on = _runs_on(job)
        for index, step in enumerate(job_steps):
            if not isinstance(step, dict):
                continue
            uses = str(step.get("uses") or "")
            if not is_cache_action(uses):
                continue
            options = step.get("with") or {}
            if not isinstance(options, dict):
                options = {}
            raw_key = options.get("key")
            steps.append(
                CacheStep(
                    workflow=str(workflow),
                    job=str(job_name),
                    index=index,
                    uses=uses,
                    key=None if raw_key is None else str(raw_key),
                    paths=_as_list(options.get("path")),
                    restore_keys=_as_list(options.get("restore-keys")),
                    runs_on=runs_on,
                )
            )
    return steps
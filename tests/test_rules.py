from __future__ import annotations

from sysopt_cachekey.rules import analyze
from sysopt_cachekey.workflow import CacheStep


def step(**overrides) -> CacheStep:
    values = {
        "workflow": "ci.yml",
        "job": "test",
        "index": 1,
        "uses": "actions/cache@v4",
        "key": "deps-${{ runner.os }}-${{ hashFiles('**/uv.lock') }}",
        "paths": ["~/.cache/pip"],
        "restore_keys": ["deps-${{ runner.os }}-"],
        "runs_on": ["ubuntu-latest"],
    }
    values.update(overrides)
    return CacheStep(**values)


def rules_for(item: CacheStep) -> list[str]:
    return [finding.rule for finding in analyze([item]).findings]


def test_a_clean_cache_step_has_no_findings():
    assert rules_for(step()) == []


def test_volatile_key_is_an_error():
    findings = analyze([step(key="cache-${{ github.sha }}", paths=["dist"])]).findings

    assert [f.rule for f in findings] == ["volatile-key"]
    assert findings[0].severity == "error"


def test_missing_key_is_an_error():
    findings = analyze([step(key=None)]).findings

    assert findings[0].rule == "missing-key"
    assert findings[0].severity == "error"


def test_missing_os_on_a_multi_os_workflow():
    item = step(
        key="deps-${{ hashFiles('**/uv.lock') }}",
        runs_on=["ubuntu-latest", "macos-latest"],
    )

    findings = analyze([item]).findings

    assert [f.rule for f in findings] == ["missing-os"]
    assert findings[0].severity == "warning"


def test_dependency_cache_without_lockfile_hash():
    item = step(key="node-deps-v1", paths=["node_modules"])

    findings = analyze([item]).findings

    assert "no-lockfile-hash" in [f.rule for f in findings]
    finding = next(f for f in findings if f.rule == "no-lockfile-hash")
    assert "package-lock.json" in finding.suggestion


def test_missing_path_is_an_error():
    findings = analyze([step(paths=[])]).findings

    assert "missing-path" in [f.rule for f in findings]
    assert any(f.severity == "error" for f in findings)


def test_broad_path_is_flagged():
    findings = analyze([step(paths=["/"])]).findings

    assert "broad-path" in [f.rule for f in findings]


def test_missing_restore_keys_is_informational():
    findings = analyze([step(restore_keys=[])]).findings

    assert [f.rule for f in findings] == ["no-restore-keys"]
    assert findings[0].severity == "info"


def test_duplicate_key_with_different_paths():
    first = step(key="shared", paths=["node_modules"])
    second = step(index=2, key="shared", paths=["~/.cache/pip"])

    findings = analyze([first, second]).findings

    assert [f.rule for f in findings].count("duplicate-key") == 2


def test_report_filters_by_severity():
    report = analyze(
        [
            step(key="cache-${{ github.sha }}", paths=["dist"], restore_keys=[]),
            step(
                index=2,
                key="deps-${{ hashFiles('**/uv.lock') }}",
                runs_on=["ubuntu-latest", "macos-latest"],
            ),
        ]
    )

    assert len(report.findings) == 3
    assert len(report.at_least("error")) == 1
    assert len(report.at_least("warning")) == 2
    assert len(report.at_least("info")) == 3
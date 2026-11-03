from __future__ import annotations

import json
from pathlib import Path

from sysopt_cachekey.cli import main

GOOD = """\
on: push
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/cache@v4
        with:
          key: pip-${{ runner.os }}-${{ hashFiles('**/uv.lock') }}
          path: ~/.cache/pip
          restore-keys: pip-${{ runner.os }}-
"""

BAD = """\
on: push
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/cache@v4
        with:
          key: pip-${{ github.run_id }}
          path: /
"""


def write(tmp_path: Path, name: str, text: str) -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def test_clean_workflow_passes(tmp_path, capsys):
    path = write(tmp_path, "ci.yml", GOOD)

    code = main([str(path)])

    assert code == 0
    assert "0 finding(s)" in capsys.readouterr().out


def test_bad_workflow_fails(tmp_path, capsys):
    path = write(tmp_path, "ci.yml", BAD)

    code = main([str(path)])

    output = capsys.readouterr().out
    assert code == 1
    assert "volatile-key" in output
    assert "broad-path" in output


def test_fail_on_none_never_fails(tmp_path):
    path = write(tmp_path, "ci.yml", BAD)

    assert main([str(path), "--fail-on", "none"]) == 0


def test_json_output(tmp_path, capsys):
    path = write(tmp_path, "ci.yml", BAD)

    code = main([str(path), "--format", "json", "--fail-on", "none"])

    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["workflows"] == 1
    assert payload["cache_steps"] == 1
    assert {finding["rule"] for finding in payload["findings"]} == {
        "volatile-key",
        "broad-path",
        "no-restore-keys",
    }


def test_directory_is_scanned_recursively(tmp_path, capsys):
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    write(workflows, "ci.yml", GOOD)
    write(workflows, "release.yaml", GOOD)

    code = main([str(workflows)])

    assert code == 0
    assert "across 2 workflow(s)" in capsys.readouterr().out


def test_no_workflows_exits_with_two(tmp_path):
    assert main([str(tmp_path)]) == 2


def test_invalid_yaml_is_reported_and_skipped(tmp_path, capsys):
    bad_yaml = write(tmp_path, "broken.yml", "jobs: [\n")
    good_yaml = write(tmp_path, "good.yml", GOOD)

    code = main([str(bad_yaml), str(good_yaml)])

    captured = capsys.readouterr()
    assert code == 0
    assert "invalid YAML" in captured.err
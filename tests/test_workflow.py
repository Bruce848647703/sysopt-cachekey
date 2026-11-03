from __future__ import annotations

from pathlib import Path

from sysopt_cachekey.workflow import (
    extract_cache_steps,
    is_cache_action,
    load_workflow,
    os_family,
)


def test_load_workflow_keeps_the_on_key(tmp_path: Path):
    path = tmp_path / "ci.yml"
    path.write_text("on: push\njobs: {}\n", encoding="utf-8")

    document = load_workflow(path)

    assert document["on"] == "push"


def test_extract_cache_steps_reads_key_paths_and_restore_keys():
    document = {
        "jobs": {
            "test": {
                "runs-on": "ubuntu-latest",
                "steps": [
                    {"uses": "actions/checkout@v4"},
                    {
                        "uses": "actions/cache@v4",
                        "with": {
                            "key": "pip-${{ runner.os }}-${{ hashFiles('**/uv.lock') }}",
                            "path": "~/.cache/pip\n.venv",
                            "restore-keys": "pip-${{ runner.os }}-\n",
                        },
                    },
                ],
            }
        }
    }

    steps = extract_cache_steps("ci.yml", document)

    assert len(steps) == 1
    step = steps[0]
    assert step.job == "test"
    assert step.index == 1
    assert step.paths == ["~/.cache/pip", ".venv"]
    assert step.restore_keys == ["pip-${{ runner.os }}-"]


def test_cache_save_and_restore_actions_are_recognised():
    assert is_cache_action("actions/cache@v4")
    assert is_cache_action("actions/cache/save@v4")
    assert is_cache_action("actions/cache/restore@v4")
    assert not is_cache_action("actions/checkout@v4")


def test_multi_os_is_detected_from_a_matrix():
    document = {
        "jobs": {
            "test": {
                "runs-on": "${{ matrix.os }}",
                "strategy": {"matrix": {"os": ["ubuntu-latest", "macos-latest"]}},
                "steps": [{"uses": "actions/cache@v4", "with": {"key": "x", "path": "y"}}],
            }
        }
    }

    step = extract_cache_steps("ci.yml", document)[0]

    assert step.multi_os is True


def test_os_family_mapping():
    assert os_family("ubuntu-latest") == "linux"
    assert os_family("macos-14") == "macos"
    assert os_family("windows-2022") == "windows"
    assert os_family("self-hosted") == ""
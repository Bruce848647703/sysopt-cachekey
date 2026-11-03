# sysopt-cachekey

Find GitHub Actions cache keys that can never hit, collide across operating
systems, or restore stale dependencies.

Cache problems are usually invisible: the job still passes, it is just slow.
This tool reads your workflow files and reports the specific patterns that make
a cache useless, with a concrete replacement key.

```text
$ sysopt-cachekey examples/bad-workflow.yml
examples/bad-workflow.yml
  test:3  error   volatile-key
      cache key contains github.run_id, which changes on every run
      -> remove the volatile token and hash the dependency files instead
  test:3  warning missing-os
      workflow runs on multiple operating systems but the key does not include runner.os
      -> prefix the key with `${{ runner.os }}-` to avoid cross-OS cache collisions
  test:3  warning no-lockfile-hash
      dependency cache key does not hash a lockfile, so stale packages can be restored
      -> include hashFiles('**/poetry.lock', '**/requirements*.txt', '**/uv.lock') in the key
  test:3  info    no-restore-keys
      cache has no restore-keys, so a near-miss key cannot provide a partial cache
      -> add a broader prefix such as `${{ runner.os }}-pip-`
  test:4  warning broad-path
      cache path '/' is too broad and can capture unrelated files
      -> cache only the dependency directory, e.g. node_modules or ~/.cache/pip
  test:4  warning missing-os
      workflow runs on multiple operating systems but the key does not include runner.os
      -> prefix the key with `${{ runner.os }}-` to avoid cross-OS cache collisions
  test:4  info    no-restore-keys
      cache has no restore-keys, so a near-miss key cannot provide a partial cache
      -> add a broader prefix such as `${{ runner.os }}-pip-`

7 finding(s): 1 error, 4 warning, 2 info across 1 workflow(s), 2 cache step(s)
```

## Install

```bash
pip install -e .
sysopt-cachekey .github/workflows

# or without installing
PYTHONPATH=src python -m sysopt_cachekey.cli .github/workflows
```

## Rules

| Rule | Severity | What it catches |
| --- | --- | --- |
| `missing-key` | error | `actions/cache` without `with.key` |
| `missing-path` | error | `actions/cache` without `with.path` |
| `volatile-key` | error | key contains `github.sha`, `github.run_id`, `github.run_number`, `github.run_attempt`, or `strategy.job-index` |
| `missing-os` | warning | multi-OS workflow whose key omits `runner.os` / `matrix.os` |
| `no-lockfile-hash` | warning | dependency cache key without `hashFiles(...)` |
| `broad-path` | warning | path is `/`, `~`, `.`, or the workspace root |
| `duplicate-key` | warning | one key reused for different paths in the same workflow |
| `no-restore-keys` | info | no `restore-keys`, so near-misses cannot partially restore |

## Usage

```bash
# scan the default location
sysopt-cachekey

# scan several files or directories
sysopt-cachekey .github/workflows examples/

# machine-readable
sysopt-cachekey .github/workflows --format json

# only fail on errors, not warnings
sysopt-cachekey .github/workflows --fail-on error

# show errors only
sysopt-cachekey .github/workflows --min-severity error
```

Exit codes: `0` clean (at the chosen threshold), `1` findings at or above
`--fail-on`, `2` no workflow could be read.

Drop it into CI to stop cache regressions:

```yaml
- name: Audit cache keys
  run: sysopt-cachekey .github/workflows --fail-on error
```

## Design notes

- Only `actions/cache`, `actions/cache/save`, and `actions/cache/restore` are
  analysed. Setup actions that manage their own cache are intentionally left
  alone.
- The lockfile suggestion is heuristic: it looks at the paths being cached and
  proposes the matching lockfile pattern, but any content-addressed input is
  fine.
- The tool never edits workflows. It reports what to change so the diff stays
  under human review.

## Development

```bash
pip install -e ".[dev]"
ruff check .
pytest -q
```

## License

MIT
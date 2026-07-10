# Offline File Agent

A small, **fully offline** agent that analyzes files on your machine and runs
rule-based automations over them. It has **zero dependencies** — everything
runs on the Python 3.9+ standard library, so it works on an air-gapped machine
and never makes a network call.

## What it does

1. **Analyze** a directory — categorize files by type, total up sizes, find the
   largest and oldest files, and detect duplicate files by content hash.
2. **Automate** — define rules in a JSON file (match conditions → actions like
   move / copy / rename / delete / log) and apply them to a folder. Runs in
   **dry-run by default**, so nothing is touched until you pass `--apply`.

## Quick start

```bash
# Analyze a folder and print a report
python -m offline_agent analyze ~/Downloads

# ...or as JSON
python -m offline_agent analyze ~/Downloads --json

# Write a starter rules file
python -m offline_agent init-rules rules.json

# Preview what the automations would do (dry-run)
python -m offline_agent run ~/Downloads --rules rules.json

# Actually perform the actions
python -m offline_agent run ~/Downloads --rules rules.json --apply
```

No installation is required — just clone the repo and run `python -m offline_agent`.

## Commands

### `analyze <dir>`
Scans a directory and prints a summary report.

| Flag | Meaning |
| --- | --- |
| `--json` | Emit machine-readable JSON instead of a text report |
| `--top N` | How many largest/oldest files to list (default 10) |
| `--no-duplicates` | Skip content-hash duplicate detection |
| `--no-recursive` | Don't descend into subdirectories |
| `--hidden` | Include dot-files and dot-directories |
| `--exclude GLOB` | Skip paths matching a glob (repeatable) |

### `run <dir> --rules <file.json>`
Applies automation rules to a directory. **Dry-run by default** — add `--apply`
to actually move/rename/delete files. Accepts the same scan flags as `analyze`.

### `init-rules [path]`
Writes a starter `rules.json` you can edit. `--force` overwrites an existing file.

## Rules format

A rules file is JSON: either a top-level array, or an object with a `"rules"`
key. Each rule has a `name`, a `match` block (conditions, all AND-ed together),
and a list of `actions`.

```json
{
  "rules": [
    {
      "name": "Sort images into sorted/images",
      "match": { "category": "image" },
      "actions": [{ "type": "move", "dest": "./sorted/images" }]
    },
    {
      "name": "Archive old logs",
      "match": { "ext": ".log", "older_than_days": 30 },
      "actions": [{ "type": "move", "dest": "./archive/logs" }]
    }
  ]
}
```

See [`examples/rules.json`](examples/rules.json) for a fuller set.

### Match conditions

| Key | Meaning |
| --- | --- |
| `name` / `name_glob` | Glob(s) matched against the file name, e.g. `"IMG_*.jpg"` |
| `name_regex` | Regular expression searched in the file name |
| `ext` | Extension(s), e.g. `".log"` or `[".jpg", ".png"]` |
| `category` | Built-in category: `image`, `document`, `data`, `audio`, `video`, `archive`, `code`, `executable`, `presentation`, `other` |
| `min_size` / `max_size` | Size threshold in bytes or a string like `"500MB"`, `"1.5k"` |
| `older_than_days` / `newer_than_days` | Age (by last-modified time) |
| `contains` | Substring that must appear in the file's text (files under 10 MB) |

A single-valued key (`ext`, `category`, `name_glob`) may be given a list to
mean "any of these".

### Actions

| Type | Fields | Effect |
| --- | --- | --- |
| `move` | `dest` | Move the file into `dest` (created if missing) |
| `copy` | `dest` | Copy the file into `dest` |
| `rename` | `template` | Rename in place using a template |
| `delete` | — | Delete the file |
| `log` | `message` | Print a message (no filesystem change) |

Relative `dest` paths resolve against the **scanned root**, not your current
directory. Destination collisions are avoided automatically (`name_1.ext`).

**Template placeholders** (usable in `dest`, `rename` templates, and `log`
messages): `{name}`, `{stem}`, `{ext}`, `{category}`, `{size}`, `{year}`,
`{month}`, `{day}`.

## Use as a library

```python
from offline_agent import scan, analyze, load_rules, AutomationEngine

files = list(scan("~/Downloads"))
report = analyze(files)
print(report.by_category, report.duplicates)

rules = load_rules("rules.json")
engine = AutomationEngine(rules, dry_run=True, base_dir="~/Downloads")
for result in engine.run(files):
    print(result)
```

## Safety notes

- `run` is **dry-run by default**; destructive actions require `--apply`.
- Files moved/deleted by one rule are not re-processed by later rules.
- The agent skips files it can't read (permission errors, broken symlinks)
  rather than crashing.

## Tests

```bash
python tests/test_agent.py       # built-in runner, no pytest needed
# or
python -m pytest -q
```

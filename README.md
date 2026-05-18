# Claude Insights

Generate focused insights reports from local Claude Code session history, with
directory-scoped analysis and explicit subagent visibility.

This repository is a portable skill/tool bundle that complements Claude Code's
built-in `/insights` command. It reads Claude Code transcript files from
`~/.claude/projects`, selects sessions by the directory where Claude Code was
run, prepares LLM-friendly Markdown packets, and lets the current assistant
write a final `report.md`.

It is designed for reports about workflow, delegation, subagent usage, friction,
and useful patterns in a specific project or branch family.

## Why Not Just Use `/insights`?

Claude Code's built-in `/insights` command is the right default for broad
personal usage analytics. It scans recent sessions, extracts facets, aggregates
usage, and writes a polished HTML report.

This tool is for a narrower use case:

- You want to analyze sessions for one project, worktree, or branch family.
- You want to understand how main-session coordination and subagents interacted.
- You want the current assistant to write a project-specific Markdown report
  from inspectable intermediate files.
- You want to compare reports written by different assistants from the same
  prepared packet set, without re-running the data extraction.

It does not try to replace `/insights`; it gives you a more inspectable,
project-scoped path when `/insights` is too broad or hides too much of the
subagent workflow.

## Differences From Built-In `/insights`

| Area | Built-in `/insights` | This tool |
|---|---|---|
| Scope | Broad recent Claude Code usage | Sessions whose `cwd` matches a directory/glob |
| Output | HTML report | Markdown packets plus assistant-written `report.md` |
| Intermediate data | Cached metadata/facets under Claude usage data | Inspectable `aggregate.json`, `index.md`, and `packets/*.md` |
| LLM flow | Internal API calls generate facets and report sections | Current assistant reads packets and writes the report |
| Subagents | Mostly visible as `Agent`/`Task` tool usage | Parent session and `subagents/*.jsonl` are separated and summarized |
| Best for | Personal usage overview and charts | Project-specific workflow review and delegation analysis |

## What It Does

- Filters Claude Code sessions by execution directory, such as
  `/path/to/project/branch_*`.
- Reconstructs the selected conversation branch from `uuid` / `parentUuid`.
- Finds subagent transcripts under each parent session's `subagents/` directory.
- Writes one Markdown packet per session with:
  - main-session timeline
  - subagent activity
  - tool counts
  - referenced files and shell commands
  - delegation and error signals
- Produces an `index.md` so the assistant can read only the packets it needs.
- Produces an `aggregate.json` with first intents, session kinds, signal
  classes, edit/write counts, verification counts, errors, interruptions,
  subagent transcript counts, logical role counts, and top files.
- Leaves final interpretation to the active assistant conversation, rather than
  starting a separate analysis process.

## Repository Layout

```text
claude-insights/
  SKILL.md
  README.md
  bin/
    collect-project-packets.py
    build-session-packet.py
  data/
    runs/
```

## Requirements

- Python 3
- Local Claude Code history at `~/.claude/projects`
- Optional: Codex or Claude Code skill support

No package install is required. The primary scripts use only the Python standard
library.

## Use As A Claude Code Skill

Link this repository as a Claude Code skill directory:

```bash
mkdir -p ~/.claude/skills
ln -s /absolute/path/to/claude-insights ~/.claude/skills/claude-insights
```

Invoke it explicitly in Claude Code:

```text
/claude-insights /path/to/project/branch_*
/claude-insights /path/to/project brief
/claude-insights /path/to/project detailed
/claude-insights /path/to/project latest:3
/claude-insights 45685c9d-0a30-4101-9924-e1eda0abc0c4 detailed
```

The skill is configured with `disable-model-invocation: true`, so it should not
start automatically from ordinary conversation. If no path/glob is provided, it
asks for the Claude Code session startup directory or cwd glob instead of
guessing from shell `pwd`.

Mode words are normalized:

- `brief`, `short`, `simple`
- `detailed`, `detail`, `deep`, `thorough`

Session IDs are supported as full UUIDs or unique UUID prefixes. In session-id
mode, the cwd path/glob is optional and `--session-id` is used internally. Latest
count requests can be expressed as `latest:N`, which maps to `--limit N`.

## Direct CLI Use

From the repository root:

```bash
python3 bin/collect-project-packets.py --limit 5 "/path/to/project/branch_*"
python3 bin/collect-project-packets.py --session-id 45685c9d-0a30-4101-9924-e1eda0abc0c4
python3 bin/collect-project-packets.py "/path/to/project" latest:3
```

On Windows, use `py` if that is the configured Python launcher.

Useful options:

```bash
python3 bin/collect-project-packets.py --session-id 45685c9d-0a30-4101-9924-e1eda0abc0c4
python3 bin/collect-project-packets.py --limit 30 --exclude-noop "/path/to/project/branch_*"
python3 bin/collect-project-packets.py --max-main-lines 180 --max-agent-lines 80 "/path/to/project/branch_*"
```

This writes a run directory:

```text
data/runs/<timestamp>/
  aggregate.json
  index.md
  next-action.json
  packets/
    <session-id>.md
```

Then ask your assistant to read `aggregate.json` and `index.md`, selectively
read packet files, and write `report.md` in the same run directory.
Avoid ad hoc `python -c` or Python heredocs for inspecting generated JSON; read
`aggregate.json` directly, or promote repeated transformations into a named
helper script under `bin/`.
The `Read` tool has a 25000-token limit. For packets with significant
non-ASCII (multibyte) text this is reached around ~40KB or ~700 lines; ASCII-
heavy packets fit more text per token, so these limits are conservative.
Inspect the `Large Packets` index section and each session's
`suggested_read_strategy` before opening a packet; for entries marked
`large_packet`, use bounded `offset`/`limit` ranges or `grep` instead of a full
read.

## Output Files

`index.md`

Small overview of the run: scope, matched sessions, packet paths, top tools, and
agent-call counts. Read this first alongside `aggregate.json`.

`aggregate.json`

Machine-readable run summary for high-limit reports. It includes per-session
first intent, session kind, substantive / low-signal / no-op classification,
report-worthy flags, edit/write count, verification count and success/failure
breakdown, error count, interruption signal, active duration, user-correction
signals, raw subagent transcript count, logical subagent role count, top files,
top tools, and recommended packet groups.

The legacy `verification_count` and `error_count` fields refer to the main
session. Subagent activity is exposed separately as `subagent_*` fields and
combined totals as `combined_*` fields. Role-level subagent statistics are
available in `subagent_role_stats`. Subagent tool counts are de-duplicated by
tool_use ID. Prefer `active_minutes_union` for elapsed role activity;
`active_minutes_cumulative` can include repeated context from resumed agents.

Report/document completeness checks such as `grep '^## ' report.md`, `wc -l`,
or `tail report.md` are counted separately as `report_verification_*` fields.
They are not included in build/test `verification_count`.

Packet sizing metadata is included as `packet_size_bytes`, `packet_line_count`,
`large_packet`, `very_large_packet`, and `suggested_read_strategy`, so report
authors can avoid full reads of large packet files.

`packets/<session-id>.md`

Detailed per-session packet. It separates main-session behavior from subagent
behavior and includes clipped timelines, tool counts, errors, referenced files,
shell commands, notable error/verification tool results, verification outcome
counts, active duration, and subagent outcome hints.

`next-action.json`

Machine-readable pointer to the index, output directory, packet count, and
session summaries.

`report.md`

Not generated by the collector. The active assistant writes this after reading
the index and selected packets.
After writing it, verify that the expected headings exist and read the beginning
and end of the file to confirm it is complete.

## Recommended Report Sections

```markdown
# Session Insights Report

## Scope

## Executive Summary

## Main Workflow Patterns

## Subagent / Delegation Patterns

## Friction and Failure Modes

## What Worked Well

## Improvements to Try

## Evidence Used

## Limits of This Report
```

## Notes

- The collector intentionally does not analyze every session by default. Use
  `--limit` to control how many recent matching sessions are packetized.
- For larger limits, read `aggregate.json` and `index.md` first, then open
  substantive packets before sampling low-signal or no-op sessions.
- Avoid ad hoc `python -c` or Python heredocs for JSON inspection; use direct
  reads, shell text tools for simple lookups, or named helper scripts.
- Packet files often exceed the Read 25000-token cap (roughly 40KB / 700 lines)
  and a few sessions can reach multi-megabyte. Read targeted sections or bounded
  line ranges instead of opening flagged packets in full.
- The packets are intermediate evidence, not the final report.
- Session duration is based on transcript timestamps and may include idle time.
- Subagent counts can be noisy when a role is recorded across multiple JSONL
  files. Treat named role flow and packet evidence as more reliable than raw
  discovered-subagent counts.
- The scripts read local Claude Code history. Review generated packets before
  sharing them outside your machine.

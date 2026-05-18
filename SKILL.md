---
name: claude-insights
description: Analyze Claude Code session history for an explicitly provided cwd/path glob and write a Markdown insights report.
argument-hint: "[path/glob] [brief|detailed]"
disable-model-invocation: true
---

# Claude Insights

Invoke this skill explicitly as `/claude-insights ...`.

Do not run this workflow automatically from ordinary conversation. This tool
analyzes Claude Code transcript files, so Claude Code is the recommended runtime
for the final report step.

## Arguments

Parse `$ARGUMENTS` as:

- target path/glob: a Claude Code session startup cwd, project directory, worktree, or glob
- mode: `brief` or `detailed`
- optional latest count: `latest:N`, or natural language such as "latest 3 sessions"
- optional session ID: a full Claude Code session UUID or unique UUID prefix

Use these canonical modes internally:

- `brief`: `brief`, `short`, `simple`
- `detailed`: `detailed`, `detail`, `deep`, `thorough`

If no target path/glob is provided, ask the user for the Claude Code session
startup directory or cwd glob and wait. Do not infer it from shell `pwd`, because
shell cwd may differ from the session startup directory after `!cd` or other
commands.

Default mode is `brief`.

If a full UUID or UUID prefix is provided, run a single-session collection with
`--session-id`. A target path/glob may still be provided to disambiguate, but it
is not required for session-id mode.

If the user asks for the latest N sessions, pass `--limit N` or include
`latest:N`.

## Collector

Run from this skill directory:

```bash
python3 bin/collect-project-packets.py --limit 20 "<path-or-glob>"
```

Use these defaults:

- `brief`: `--limit 10`
- `detailed`: `--limit 30`

Useful optional flags:

```bash
--session-id 45685c9d-0a30-4101-9924-e1eda0abc0c4
--exclude-noop
--max-main-lines 180
--max-agent-lines 80
--max-agents 12
```

## Report Workflow

1. Run the Python collector.
2. Read `aggregate.json` and `index.md` first.
3. Use `recommended_packets` and `report_flags` to choose packet files.
4. Open only selected `packets/*.md`; do not read every packet blindly.
5. Preserve the distinction between main-session behavior and subagent behavior.
6. Write `report.md` in the generated output directory.
7. After writing `report.md`, verify that the expected section headings exist
   and read the beginning and end of the file to confirm it is complete.

Do not use ad hoc `python -c`, `python3 -c`, or Python heredocs from Bash just
to inspect `aggregate.json` or `index.md`. Prefer reading those files directly.
If `aggregate.json` itself exceeds the per-call Read token limit (typical for
runs of 10+ sessions, where the file can reach 100KB+), read it in bounded
`offset`/`limit` ranges (for example, the `totals` and `subagent_role_stats`
header first, then targeted slices of the `sessions` array) rather than falling
back to ad hoc `python3 -c`. The per-call Read limit is independent of the
session context window, so a few bounded reads cost almost no context.
If a repeated JSON transformation becomes necessary, add a named helper script
under `bin/` so the behavior is reviewable and reusable.

For `brief`, open only the strongest recommended packets, usually 2-4 packets.
For `detailed`, use more of `recommended_packets`, but do not open every entry
in parallel. Skip sessions whose signals are already covered by an earlier
packet, and target roughly 50-80K tokens of total opened packet content.

The `Read` tool has a 25000-token limit. Non-ASCII (multibyte) text consumes
roughly 2 bytes per token, so a packet with significant non-ASCII content at
or above ~40KB or ~700 lines can truncate on a full read. Pure-ASCII packets
fit more text per token, so these limits are conservative. Before opening any
packet:

1. Check `packet_size_bytes`, `packet_line_count`, `large_packet`,
   `very_large_packet`, and `suggested_read_strategy` for that session in
   `aggregate.json`, and the `Large Packets` index section.
2. If `large_packet` is true, do not full-read. Use `offset`/`limit` to read
   bounded ranges around the relevant headings (Metadata, Main Signals, Notable
   Tool Results, Agent Activity) or use `grep` for targeted lookups.
3. Treat the `Large Packets` index list as the authoritative blocklist for
   full reads; the per-session `suggested_read_strategy` string repeats the
   same signal.

## Packet Selection

Prefer packets in this order:

1. `recommended_packets.agent_heavy`
2. `recommended_packets.error_heavy`
3. `recommended_packets.verification_heavy`
4. `recommended_packets.interrupted`
5. `recommended_packets.representative`
6. `recommended_packets.noop_examples`, only if no-op rate is report-worthy

Use `index.md` flags to refine the selection:

- `agent-heavy`
- `error-heavy`
- `verification-heavy`
- `edit-heavy`
- `interrupted`
- `user-correction`
- `docs`
- `implementation`

For subagent analysis, compare `raw_subagent_transcript_count` with
`logical_subagent_role_count`; raw transcripts can be split across files, while
logical roles come from parent delegation labels.

Also inspect `subagent_role_stats`, `subagent_*`, and `combined_*` fields in
`aggregate.json`. The legacy `verification_count` and `error_count` fields are
main-session counts; subagent verification and errors are reported separately.
Report/document completeness checks are counted separately in
`report_verification_*` fields and are not included in build/test
`verification_count`.
Subagent tool counts are de-duplicated by tool_use ID. Prefer
`active_minutes_union` for elapsed role activity; `active_minutes_cumulative`
can include repeated context from resumed agents.

## Report Shape

Use these sections unless the user asks otherwise:

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

Keep reports concise in `brief` mode. In `detailed` mode, include more evidence
and more packet IDs, but still summarize rather than pasting packet content.

## Future Experiment

Do not add `context: fork` yet. It should be tested separately after this
slash-skill workflow is stable. Useful questions to test:

- whether a forked skill can use subagents or team/fork features recursively
- whether forked analysis improves report quality
- whether intermediate files can be simplified if recursive subagent analysis is reliable
- how forked skill execution appears in Claude Code logs when analyzed by this tool

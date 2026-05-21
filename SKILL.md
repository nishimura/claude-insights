---
name: claude-insights
description: Analyze Claude Code session history for an explicitly provided cwd/path glob and write a Markdown insights report.
argument-hint: "[path/glob] [brief|normal|deep]"
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
- mode: `brief`, `normal`, or `deep`
- optional latest count: `latest:N`, or natural language such as "latest 3 sessions"
- optional session ID: a full Claude Code session UUID or unique UUID prefix

Use these canonical modes internally:

- `brief`: `brief`, `short`, `simple`
- `normal`: `normal`, `default`, `standard`, `regular`, `usual`
- `deep`: `detailed`, `detail`, `deep`, `thorough`, `extensive`

If no target path/glob is provided, ask the user for the Claude Code session
startup directory or cwd glob and wait. Do not infer it from shell `pwd`, because
shell cwd may differ from the session startup directory after `!cd` or other
commands.

Default mode is `normal`.

If a full UUID or UUID prefix is provided, run a single-session collection with
`--session-id`. A target path/glob may still be provided to disambiguate, but it
is not required for session-id mode.

If the user asks for the latest N sessions, pass `--limit N` or include
`latest:N`.

## Collector

Before running the collector, create a small temporary correction keyword file
for this run. Include the English base ideas plus likely synonyms in the user's
current language or the language visible in the target sessions. This is a
lightweight hint list for user-correction candidate detection, not a hard
verdict list. Prefer concrete correction phrases over short generic words; avoid
terms that mostly indicate ordinary design questions.

Use a unique temporary file path for each run:

```bash
mkdir -p /tmp/claude-insights-keywords
KEYWORDS_FILE="/tmp/claude-insights-keywords/correction-keywords-$(date +%Y%m%d_%H%M%S).txt"
```

Run from this skill directory:

```bash
python3 bin/collect-project-packets.py --correction-keyword-file "$KEYWORDS_FILE" --limit 20 "<path-or-glob>"
```

Use these defaults:

- `brief`: `--limit 10`
- `normal`: `--limit 30`
- `deep`: `--limit 40 --exclude-noop --max-main-lines 320 --max-agent-lines 180`

Useful optional flags:

```bash
--session-id 45685c9d-0a30-4101-9924-e1eda0abc0c4
--correction-keyword-file "$KEYWORDS_FILE"
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

Modes change evidence budget and sampling strategy, not the kind of conclusion
you should force. `brief` may still report a severe finding; `deep` may still
produce a short report if the evidence is simple.

- `brief`: open the strongest 2-4 recommended packets.
- `normal`: cover the main recommended packets without opening duplicates;
  target roughly 50-80K tokens of opened packet content.
- `deep`: add non-overlapping packets and bounded ranges from large packets;
  target roughly 75-120K tokens, while respecting the per-call Read limit.

In `deep` mode, use three second-opinion reviewers when subagents are available
and there are multiple substantive packets or any Large Packets. If you skip
reviewers in that case, state the reason in Evidence Used or Limits. The main
session remains responsible for primary analysis and the final report.
Reviewers are not section writers:

- bad points: friction, missed opportunities, user corrections, repeated
  failures, weak delegation, and evidence that contradicts an optimistic
  reading
- good points: workflows that worked, useful delegation, strong verification,
  reusable habits, and evidence that contradicts an overly negative reading
- tool-use quality: all tool usage as a whole, judged by whether it materially
  advanced the task, produced reliable evidence, avoided needless detours, and
  correctly separated noisy tool errors from real blockers

Give reviewers shared context rather than an answer-shaped scope: the run
directory, `aggregate.json`, `index.md`, packet list, Large Packet entries, and
any user-provided focus. Starting points are allowed but non-exclusive. Remind
reviewers to choose their own grep targets and bounded ranges, and never
full-read Large Packets.

Ask reviewers for top findings, evidence, importance, and contradictions. Do
not paste reviewer prose into `report.md`; incorporate only supported findings
that materially change or strengthen the final report.

If the user provides a natural-language focus, use it to guide packet selection
and local-file interpretation. The focus may be a skill, command, feature, file
area, failure mode, workflow pattern, or other topic. Use `aggregate.json`,
`index.md` Focus Hints, first intents, top files, flags, and targeted grep to
identify likely evidence. Read related local files only when they help interpret
the focus; do not limit this behavior to skill definitions.

A focus narrows the question, not the evidence search. In `deep` mode, inspect
focused packets plus a small contrast set of adjacent, representative,
error-heavy, or verification-heavy sessions. Use the focus to organize the
report, not to pre-answer it.

Avoid interrupting focused reports with clarification questions unless the
focus cannot be identified or a wrong assumption would make the report
misleading. Prefer writing explicit assumptions and limits, then let the user
correct the interpretation in a follow-up.

Apply chronological caution. Current files, docs, skills, and tests may differ
from the versions that existed during older sessions. When comparing historical
session behavior to current files, frame differences as possible evolution,
drift, observed mismatch, or follow-up checks unless the packet shows the same
rule or file content existed at that time.

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

Start from this section set unless the user asks otherwise:

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

## Diagnostics Notes

## Limits of This Report
```

These sections are defaults, not quotas. Do not invent weak positives,
negatives, or improvements to fill them. Merge, shorten, or omit sections that
have no material evidence. Use subsection headings only when they make
high-signal findings easier to follow.

Write ordinary project reports so `report.md` is understandable without
`aggregate.json`, `index.md`, packet metadata, or collector counts. Keep
collector field names and collector-derived totals out of the Executive
Summary: edit/write totals, verification totals, error totals, subagent error
totals, raw/logical transcript counts, active-minute totals, and `role_stats`
counts. This applies even when the totals are written in natural language, such
as "main 32 / subagent 14 / total 46 errors." Executive Summary counts are
acceptable only when they are direct reader-facing project facts, such as
sessions reviewed, domain object counts, or test results like
`PHPUnit 8/8 passed`.

Put raw fields and parser caveats in Evidence Used, Diagnostics Notes, or
Limits of This Report when they matter for verification. A normal reader should
not need those sections to understand the report.

For focused or chronology-sensitive reports, prefer evidence-backed
observations and hypotheses over hard verdicts. Include assumptions and
follow-up checks when a later improvement session or a current file should
validate the interpretation.

## Self-Test Mode

If the user invokes `/claude-insights self-test ...`, read
[self-test.md](self-test.md) for the full self-test workflow, required checks,
and verdict format. Do not load this file for ordinary project reports.

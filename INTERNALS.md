# Claude Insights Internals

This document records implementation details and report-authoring guidance that
are useful for maintaining `claude-insights`, but too detailed for `README.md`.

## Direct CLI Use

From the repository root:

```bash
python3 bin/collect-project-packets.py --limit 5 "/path/to/project/branch_*"
python3 bin/collect-project-packets.py --session-id 45685c9d-0a30-4101-9924-e1eda0abc0c4
python3 bin/collect-project-packets.py "/path/to/project" latest:3
python3 bin/collect-project-packets.py --correction-keyword-file /tmp/claude-insights-keywords/correction-keywords-20260520_120000.txt "/path/to/project"
```

On Windows, use `py` if that is the configured Python launcher.

Useful options:

```bash
python3 bin/collect-project-packets.py --session-id 45685c9d-0a30-4101-9924-e1eda0abc0c4
python3 bin/collect-project-packets.py --limit 30 --exclude-noop "/path/to/project/branch_*"
python3 bin/collect-project-packets.py --limit 40 --exclude-noop --max-main-lines 320 --max-agent-lines 180 "/path/to/project/branch_*"
python3 bin/collect-project-packets.py --max-main-lines 180 --max-agent-lines 80 "/path/to/project/branch_*"
```

The collector writes a run directory:

```text
data/runs/<timestamp>/
  aggregate.json
  correction-keywords.txt
  index.md
  next-action.json
  packets/
    <session-id>.md
```

After collection, the active assistant should read `aggregate.json` and
`index.md`, selectively read packet files, and write `report.md` in the same
run directory.

Avoid ad hoc `python -c` or Python heredocs for inspecting generated JSON. Read
`aggregate.json` directly, use shell text tools for simple lookups, or promote
repeated transformations into a named helper script under `bin/`.

## Output Files

### `index.md`

Small overview of the run: scope, matched sessions, packet paths, top tools,
and agent-call counts. It also includes Focus Hints such as slash commands,
skill base directories, and top skill/doc files when available. Read this first
alongside `aggregate.json`.

### `aggregate.json`

Machine-readable run summary for higher-limit reports. It includes per-session
first intent, session kind, substantive / low-signal / no-op classification,
report-worthy flags, edit/write count, verification count and success/failure
breakdown, error count, interruption signal, active duration, user-correction
signals, raw subagent transcript count, logical subagent role count, top files,
top tools, and recommended packet groups.

It also includes slash command metadata and skill base directories when they are
visible in the session transcript.

The `correction_keywords` object records the source keyword file, saved run
copy, keyword count, and actual keyword list used for user-correction candidate
detection.

The legacy `verification_count` and `error_count` fields refer to the main
session. Subagent activity is exposed separately as `subagent_*` fields and
combined totals as `combined_*` fields. Role-level subagent statistics are
available in `subagent_role_stats`.

Subagent tool counts are de-duplicated by tool-use ID. Prefer
`active_minutes_union` for elapsed role activity; `active_minutes_cumulative`
can include repeated context from resumed agents.

Report/document completeness checks such as `grep '^## ' report.md`, `wc -l`,
or `tail report.md` are counted separately as `report_verification_*` fields.
They are not included in build/test `verification_count`.

A Bash command counts as verification when one of its simple commands (split at
newlines, `;`, `&&`, `||`, and `|`, outside quotes) runs a test runner, linter,
type checker or build (`phpunit`, `phpstan`, `pytest`, `npm test`, `make check`,
`php artisan test`, `./run-tests.sh`, ...). Simple commands that start with a
command that only reads or moves files (`grep`, `sed`, `cat`, `git`, `ls`,
`find`, ...) never count, so `grep -rn phpunit .` or `sed -n 1,40p
tests/FooTest.php` are not verification. Heredoc bodies and redirection targets
are ignored, and `bash -c '...'` is looked into.

Packet sizing metadata is included as `packet_size_bytes`, `packet_line_count`,
`large_packet`, `very_large_packet`, and `suggested_read_strategy`, so report
authors can avoid full reads of large packet files.

Per-session `user_correction_examples` contains short user-message excerpts that
matched the correction keyword list. Treat them as review candidates, not proof
that the assistant made a mistake.

### `correction-keywords.txt`

The normalized keyword list used for this run. The active assistant creates a
temporary keyword file before collection; the collector copies the normalized
English base terms plus run-specific terms into the run directory so self-test
and later review can see exactly what was used.

### `packets/<session-id>.md`

Detailed per-session packet. It separates main-session behavior from subagent
behavior and includes clipped timelines, tool counts, errors, referenced files,
shell commands, notable error/verification tool results, verification outcome
counts, active duration, model-invocation tool signals, and subagent outcome
hints.

The timeline follows one branch of the `parentUuid` tree: the branch whose last
message was written last, as Claude Code picks when it resumes. Older attempts
that the user rewound or edited are left out. The walk crosses compactions
through `logicalParentUuid` (a compact boundary has `parentUuid: null`), so a
packet covers the whole session, not only the part after the last compaction.
Parallel tool calls in one response leave dead-end sibling branches; they are
put back into the timeline (same `message.id`, and the results of those tool
calls).

Packets also show the full-session delegation call count and any calls outside
the selected branch when those counts differ; such calls come from rewound
attempts. Delegation calls are `Agent`, `Workflow`, and the old `Task` name.

Timeline lines are labeled by who produced them. Only `[User]` lines are text a
person typed (or a subagent's task prompt). `[Task notification]` is a
subagent's completion notice, `[Agent message]` is a message from another agent
(such as a subagent hand-back), and `[System]` / `[System: <kind>]` lines are
inserted by Claude Code (skill bodies, system reminders, local command output).

Each subagent section shows `Agent type`, `Description`, and `Workflow phase`
from the `agent-<id>.meta.json` file beside the transcript when it exists.

Model-invocation signals are collected for `Agent` and `Workflow`, plus
`TeamCreate` (removed in Claude Code 2.1.178) and `Task` (the old name of the
Agent tool) for older sessions.
For each call, the collector records the assistant message `model`, delegation
labels such as `team_name`, `agent_type`, `subagent_type`, and any tool input
field whose key contains `model`. The assistant message model shows which model
issued the tool call; it is not proof that the tool explicitly selected that
model. Treat explicit selection as present only when `model_invocation_model_fields`
or `model_invocation_tools_with_model_field_count` is non-zero.

### `next-action.json`

Machine-readable pointer to the index, output directory, packet count, and
session summaries.

### `report.md`

Not generated by the collector. The active assistant writes this after reading
the index and selected packets.

After writing it, verify that the expected headings exist and read the beginning
and end of the file to confirm it is complete.

Reports use a stable default shape, but the assistant may merge thin sections or
use subsection headings when that makes the findings clearer.

For `deep` reports, the active assistant may use subagents as second-opinion
reviewers before writing `report.md`. This is an analysis workflow only; the
collector output format does not change. The main session still owns the
primary analysis, packet selection, Large Packet safety, final interpretation,
and report writing.

Recommended second-opinion reviewers are bad points, good points, and tool-use
quality. In `deep` mode, use all three when the evidence size justifies it; if a
reviewer is skipped, note why in report limits or evidence notes. The tool-use
reviewer should evaluate all tool usage as a whole: did it materially advance
the task, produce reliable evidence, avoid needless detours, and separate noisy
tool errors from real blockers? Do not overemphasize minor tool errors unless
they changed the solution, caused rework, or exposed a recurring workflow
problem.

Each reviewer should receive shared context rather than a narrow answer-shaped
scope: the run directory, `aggregate.json`, `index.md`, packet list, Large
Packet entries, and any user-provided focus. The main session may provide
starting points, but should state that they are not exclusive and that the
reviewer should choose its own grep targets and bounded ranges. Always include
an explicit reminder not to full-read packets listed in the Large Packets
section.

Reviewer outputs should be structured notes: top findings, evidence, why it
matters, whether it should change the final report, and any important evidence
that contradicts the main session's likely interpretation. The final report
should be synthesized by the main session rather than assembled from copied
subagent prose.

For `deep` reports, the assistant should write `findings.md` before
`report.md`. This file is a discovery ledger, not a collector output and not a
polished report. It records which discovery checks were performed, the
candidate findings found by the main session or reviewers, each finding's
evidence and impact, and the final placement decision after `report.md` is
written.

Use final statuses such as `included`, `diagnostics`, `evidence_only`, `limits`,
`omitted_low_materiality`, `omitted_unverified`, and `contradicted`. The goal is
to separate discovery from report synthesis: material findings should not
disappear only because the final report is concise.

Ordinary project reports should be readable as standalone narratives. Do not
assume the reader has seen `aggregate.json`, `index.md`, packet metadata, or
collector field names. Keep raw diagnostic counts, field names, and
collector-derived totals out of the Executive Summary. This includes
edit/write totals, verification totals, error totals, subagent error totals,
raw/logical transcript counts, active-minute totals, and `role_stats` counts.
Counts are acceptable in the Executive Summary only when they are direct
reader-facing project facts, such as the number of sessions reviewed, a domain
object count, or a test result like `PHPUnit 8/8 passed`. Translate internal
metrics into reader-facing observations in the main sections.

Use `Diagnostics Notes` for verification-oriented details that are still worth
preserving: internal counts such as `combined_error_count`, raw vs logical
subagent counts, Large Packet handling, off-chain Agent/Task call caveats,
second-opinion reviewer count or scope caveats, and differences between
reviewer-derived counts and collector counts. `Evidence Used`, `Diagnostics
Notes`, and `Limits of This Report` are the right places for these references;
the Executive Summary is not.

Reports may compare historical sessions with current project files when that
helps interpretation. Such comparisons should be framed chronologically:
current files, docs, skills, and tests may differ from the versions that existed
during older sessions.

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

## Diagnostics Notes

## Limits of This Report
```

## Modes

Mode defaults are defined in `SKILL.md`:

- `brief`: `--limit 10`
- `normal`: `--limit 30`
- `deep`: `--limit 40 --exclude-noop --max-main-lines 320 --max-agent-lines 180`

Modes change the evidence budget and sampling strategy more than the importance
threshold. `deep` reads more evidence, but it does not guarantee that all
`brief` or `normal` findings will appear in the final report.

For important retrospectives, compare multiple modes or ask for a synthesis
across runs.

## Large Packet Handling

The `Read` tool has a 25000-token limit. For packets with significant non-ASCII
text this is often reached around 40KB or 700 lines; ASCII-heavy packets fit
more text per token, so these limits are conservative.

Inspect the `Large Packets` index section and each session's
`suggested_read_strategy` before opening a packet. For entries marked
`large_packet`, use bounded line ranges or targeted grep instead of a full read.

Very large packets can reach several megabytes. Treat them as grep targets and
read only the relevant sections.

## Focus And Chronology

Focused reports can use natural-language arguments such as a skill, command,
feature, file area, failure mode, workflow pattern, or current reference file.

A focus should narrow the question, not the evidence search. In `deep` mode,
focused reports should still inspect focused packets plus a contrast set:
adjacent workflows, representative non-focused sessions, and relevant
error-heavy or verification-heavy sessions. Use the focus to organize the
analysis and decide what to emphasize, not to shrink the evidence budget.

Current files are latest-state references. They are useful for interpretation,
but they do not prove that older sessions violated current rules. When comparing
historical session behavior to current files, frame differences as possible
evolution, drift, observed mismatch, or follow-up checks unless packet evidence
shows the same rule existed at the time.

User-provided focus context should override generic classification. For example,
if the user says a workflow guide is project-specific and maintained in another
repository, do not reclassify it as a generic tool unless the evidence clearly
shows otherwise.

Avoid hard words such as "violation" unless there is evidence that the rule
existed at the time and was intended to be strict.

## User-Correction Keywords

Every skill run should create a small temporary keyword file before invoking
the collector. Use a dedicated temporary directory and a timestamped filename,
for example
`/tmp/claude-insights-keywords/correction-keywords-<timestamp>.txt`, so repeated
runs do not overwrite each other or trigger overwrite prompts.

Include English base terms plus likely synonyms in the user's current language
or the language visible in the target sessions. Prefer concrete correction
phrases over short generic words, and avoid terms that mostly indicate ordinary
design questions.

The keyword file is intentionally lightweight and may vary by run. It improves
recall for messages such as corrections, misunderstandings, retries, preference
reversals, or missing requirements. The collector saves the normalized list to
`data/runs/<timestamp>/correction-keywords.txt` and records it in
`aggregate.json`.

Because this is keyword-based, false positives are expected. Use the resulting
`user-correction` flag and `user_correction_examples` as packet-selection hints,
not as final judgments.

ASCII keywords are matched with word boundaries at the beginning and end when
they start or end with ASCII word characters. This prevents short terms such as
`no` from matching inside `not`, while still allowing non-ASCII phrase matching.

## Self-Test Mode

Use self-test when you want to analyze a previous `claude-insights` execution
itself rather than the target project:

```text
/claude-insights self-test <session-id>
```

Prefer an explicit session ID. Avoid `latest:1` for self-test unless you have
confirmed the target session, because it can select the current self-test
session instead of the previous run.

Self-test should write `self-test-report.md`. It checks log-format health,
parser behavior, numeric consistency, direct `aggregate.json` / `index.md`
reads, large-packet handling, report verification, and accidental ad hoc
`python -c` usage.

## Caveats

- The collector intentionally does not analyze every session by default. Use
  mode defaults or `--limit` to control how many recent matching sessions are
  packetized.
- For larger limits, read `aggregate.json` and `index.md` first, then open
  substantive packets before sampling low-signal or no-op sessions.
- The packets are intermediate evidence, not the final report.
- Session duration is based on the timestamps of user and assistant entries and
  may include idle time. System entries such as `away_summary`, written minutes
  after a turn, are not counted.
- An interruption is a person's user entry whose text starts with
  `[Request interrupted by user`. A subagent hand-back or peer message that
  quotes that text is not an interruption.
- A subagent's Outcome is `completed` when it called `SubagentHandback` (current
  subagents end this way) or `StructuredOutput` (Workflow agents return their
  result this way), reported with `SendMessage`, or its `.meta.json` says
  `finished: true`.
- Shell command lists in packets are capped by `--max-commands`; the heading
  says `(showing first N of M)` when commands were left out.
- Subagent counts can be noisy when a role is recorded across multiple JSONL
  files. Treat named role flow and packet evidence as more reliable than raw
  discovered-subagent counts.
- Human user messages are told apart from inserted ones by `origin.kind` in
  recent transcripts. Older transcripts have no `origin`; there `isMeta` and
  known text prefixes (`<task-notification>`, `Another Claude session sent a
  message:`, `<system-reminder>`, local command output, ...) decide.
- Only `agent-*.jsonl` files under `subagents/` are agent transcripts. Other
  JSONL files there, such as a workflow's `journal.jsonl`, are skipped. The
  role of a subagent comes from `agentType` in its `.meta.json` when present,
  and is otherwise inferred from the parent's delegation call and task text.
- Files that Bash commands changed (`sed -i`, heredoc, ...) are read from
  `toolUseResult.bashEditDiff`, and each such command counts as one edit in
  `edit_write_count`. `bash_edit_count` is that Bash share. Claude Code records
  only files inside the session's working directories there.
- The scripts read local Claude Code history. Review generated packets before
  sharing them outside your machine.

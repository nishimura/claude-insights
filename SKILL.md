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

Use these canonical modes internally:

- `brief`: `brief`, `short`, `simple`
- `detailed`: `detailed`, `detail`, `deep`, `thorough`

If no target path/glob is provided, ask the user for the Claude Code session
startup directory or cwd glob and wait. Do not infer it from shell `pwd`, because
shell cwd may differ from the session startup directory after `!cd` or other
commands.

Default mode is `brief`.

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

For `brief`, open only the strongest recommended packets, usually 2-4 packets.
For `detailed`, use more of `recommended_packets`, but still avoid opening every
packet unless needed.

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

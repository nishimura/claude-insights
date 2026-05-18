---
name: claude-insights
description: Generate insights reports from local Claude Code session history scoped by execution directory globs, especially sessions with subagent activity. Use when the user asks to analyze Claude Code sessions, inspect agent delegation, or create an insights report for directories like /path/to/project/branch_*.
---

# Claude Insights

Use this skill to create an insights report from local Claude Code session logs. The current assistant performs the analysis in the conversation after deterministic scripts prepare scoped Markdown packets.

The skill directory is the directory containing this `SKILL.md`. Run bundled scripts from that directory.

## Workflow

1. Ask for or infer one or more execution-directory patterns, for example:

```text
/home/user/project/branch_*
```

2. Run the collector:

```bash
python3 bin/collect-project-packets.py --limit 20 "/path/to/project/branch_*"
```

If not running from the skill directory, use the absolute path to this skill's `bin/collect-project-packets.py`.

3. Read only the generated `aggregate.json` and `index.md` first. They list packet files, scope metadata, session kinds, first intents, signal classes, edit/write counts, verification counts, errors, interruption signals, raw subagent transcript counts, logical subagent role counts, and top files.

4. Read selected packet files as needed. Do not read every packet blindly when many sessions match.

5. Write `report.md` in the generated output directory. Keep it concise, evidence-based, and focused on the selected Claude Code sessions.

## Packet Selection Strategy

When `--limit` is high, use this order instead of opening every packet:

1. Start from `aggregate.json` to identify session-kind distribution, no-op / low-signal noise, top files, interrupted sessions, and sessions with errors.
2. Use `index.md` to choose packets with substantive signal first, especially delegated, implementation, verification, error-heavy, or interrupted sessions.
3. Sample at most a few low-signal or no-op packets when they explain scope noise, aborted work, or repeated setup friction.
4. For subagent analysis, compare `raw_subagent_transcript_count` with `logical_subagent_role_count`; raw transcripts can be split across files, while logical roles come from parent delegation labels.
5. Record which packets were opened in the report's Evidence section.

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

If the user later wants model-to-model comparison, generate separate reports from the same `index.md`/packet set and compare those reports as a separate task. Do not put speculative model comparisons inside a single-session-log report.

## Constraints

- Do not start a separate LLM process for the analysis unless the user explicitly asks. Use scripts only to prepare packet files; the current assistant should read the generated packet files and write the report.
- Keep large intermediate data out of the conversation. Start from `aggregate.json` and `index.md`, then open only relevant packet files.
- Preserve the distinction between main-session behavior and subagent behavior.
- Use the generated packet paths; do not inspect raw `~/.claude/projects` logs unless packet generation fails.

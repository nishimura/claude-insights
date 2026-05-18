# Self-Test Mode

Use this mode only when the user explicitly asks for `self-test`.

Usage:

```text
/claude-insights self-test <session-id>
```

Do not use `latest:1` for self-test unless the user explicitly confirms the
target session. It can accidentally select the current self-test session rather
than the previous claude-insights run.

Self-test analyzes a previous claude-insights execution. The goal is not project
insight. The goal is to check whether this skill still reads Claude Code logs
correctly and whether the previous run followed this skill's workflow.

## Self-Test Workflow

1. Run the collector with `--session-id <session-id>`.
2. Read `aggregate.json`, `index.md`, and the single packet.
3. Read the relevant parts of `bin/collect-project-packets.py` and
   `bin/build-session-packet.py` before judging parser behavior.
4. Write `self-test-report.md`, not `report.md`.

## Required Self-Test Checks

- Confirm exactly one session was packetized.
- Confirm `session_kind`, `signal_class`, `top_tools`, and shell commands match
  the packet timeline.
- Verify numeric consistency:
  - `top_tools` counts vs Main Timeline tool markers.
  - `report_verification_count` vs shell commands that inspect `report.md`.
  - `error_count` vs tool_result blocks with `is_error=true`.
  - `verification_count` vs build/test/lint commands only.
  - `raw_subagent_transcript_count` and `logical_subagent_role_count`, if present.
- Confirm `python -c` and Python heredocs were not used for JSON inspection.
- Confirm `aggregate.json` and `index.md` were read directly.
- Confirm large packets were not full-read.
- Confirm `report.md` was written and then checked with headings and tail/end
  inspection.
- Check for token-limit errors, missing sections, empty timeline, empty tools,
  or suspicious unknown block types.
- If the packet contains subagents, verify role names against parent Agent input
  and the first user message; do not trust summary text such as `OK`.

## Self-Test Verdict

End with one of:

- `PASS`
- `PASS with warnings`
- `FAIL`

Include concrete evidence for warnings or failures.

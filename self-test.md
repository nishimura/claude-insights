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
4. Summarize the expected intermediate file formats from the Python code:
   `aggregate.json`, `index.md`, `next-action.json`, and `packets/<session>.md`.
5. Write `self-test-report.md`, not `report.md`.

## Required Self-Test Checks

- Confirm exactly one session was packetized.
- Confirm `correction-keywords.txt` exists in the run directory when correction
  keywords were used, and that `aggregate.json` records the keyword count and
  saved file path.
- Confirm the report includes a short "Expected Intermediate Formats" section
  based on the Python code, not only on generated examples.
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
- For ordinary project reports, confirm internal collector field names and raw
  diagnostic counts are not placed in the Executive Summary. If the report has
  `Diagnostics Notes`, check its internal metrics and caveats against
  `aggregate.json`, `index.md`, and packet evidence.

## Expected Intermediate Formats

The self-test report must briefly describe the expected shape of these files,
based on reading `bin/collect-project-packets.py` and
`bin/build-session-packet.py`:

- `aggregate.json`: top-level `totals`, `session_kinds`,
  `recommended_packets`, `subagent_role_stats`, and `sessions`; per-session
  records should include counts, flags, packet metadata, top files/tools, and
  subagent summaries. It should also include `correction_keywords` metadata.
- `index.md`: Scope, Aggregate Signals, optional Subagent Role Stats, optional
  Large Packets, Recommended Packets, Packetized Sessions, and Report Guidance.
- `next-action.json`: output directory, index path, aggregate path, packet
  count, session summaries, and suggested next step.
- `packets/<session>.md`: Metadata, Main Intent, Main Timeline, Main Signals,
  optional Notable Main Tool Results, Agent Activity, and Combined Delegation
  Signals.
- `correction-keywords.txt`: normalized run-local keyword list, if correction
  keywords were used.

If the generated files do not match this expected shape, report `FAIL` or
`PASS with warnings` with concrete missing fields or sections.

## Self-Test Verdict

End with one of:

- `PASS`
- `PASS with warnings`
- `FAIL`

Include concrete evidence for warnings or failures.

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
- You want to continue investigating from the same assistant conversation after
  the first report is written.
- You want to compare reports written by different assistants from the same
  prepared packet set, without re-running the data extraction.

It does not try to replace `/insights`; it gives you a more inspectable,
project-scoped path when `/insights` is too broad or hides too much of the
subagent workflow. Because the report is written by the active assistant, you
can continue asking follow-up questions with the report context still loaded.
The tradeoff is that unrelated prior conversation can also affect the report;
start from a dedicated session when you want a cleaner analysis context.

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
  - model-invocation signals for `TeamCreate`, `Agent`, and `Task`
- Produces an `index.md` so the assistant can read only the packets it needs.
- Produces an `aggregate.json` with first intents, session kinds, signal
  classes, edit/write counts, verification counts, errors, interruptions,
  subagent transcript counts, logical role counts, model-invocation tool
  signals, assistant model distribution, and top files.
- In `deep` mode, the active assistant may use second-opinion subagents for
  bad points, good points, and tool-use quality while keeping the main session
  responsible for final synthesis.
- In `deep` mode, writes a `findings.md` discovery ledger before the final
  report so material findings are not lost during summarization.
- Keeps the main report narrative readable on its own, while preserving raw
  collector metrics and parser caveats in evidence or diagnostics sections.
- Leaves final interpretation to the active assistant conversation, rather than
  starting a separate analysis process.

## Repository Layout

```text
claude-insights/
  SKILL.md
  SKILL_ja.md
  README.md
  INTERNALS.md
  self-test.md
  bin/
    collect-project-packets.py
    build-session-packet.py
  data/
    runs/
```

## Requirements

- Python 3
- Local Claude Code history:
  - macOS/Linux/WSL: `~/.claude/projects`
  - Windows: `%USERPROFILE%\.claude\projects`
- Optional: Codex or Claude Code skill support

No package install is required. The primary scripts use only the Python standard
library.

For collector internals, output file details, self-test mode, and direct CLI
debugging, see [INTERNALS.md](INTERNALS.md).

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
/claude-insights /path/to/project normal
/claude-insights /path/to/project detailed
/claude-insights /path/to/project latest:3
/claude-insights 45685c9d-0a30-4101-9924-e1eda0abc0c4 detailed
/claude-insights /path/to/project deep investigate the review workflow; the current workflow guide is /path/to/docs/review-workflow.md
```

The skill is configured with `disable-model-invocation: true`, so it should not
start automatically from ordinary conversation. If no path/glob is provided, it
asks for the Claude Code session startup directory or cwd glob instead of
guessing from shell `pwd`.

Mode words are normalized:

- `brief`, `short`, `simple`
- `normal`, `default`, `standard`, `regular`, `usual`
- `detailed`, `detail`, `deep`, `thorough`, `extensive`

Default report mode is `normal`, which uses the previous detailed profile.
Use `brief` only for a lightweight pass. Use `detailed` / `deep` / `thorough`
when you want a deeper pass that reads more packet evidence without full-reading
large packets.

When `deep` mode has enough evidence and subagents are available, the assistant
may use up to three second-opinion reviewers: bad points, good points, and
tool-use quality. These reviewers are not section writers. They receive shared
run context and Large Packet constraints, choose their own bounded ranges or
grep targets, and return notes for the main assistant to synthesize.

Modes are not strictly hierarchical. `deep` reads more evidence, but it does
not fully contain `brief` or `normal`: different sampling can emphasize
different useful findings, especially for large or unusually complex projects.
For important retrospectives, compare multiple modes or ask for a synthesis
across runs.

You can also ask for a focused report in natural language, such as a specific
skill, command, feature, file area, failure mode, or workflow pattern. The
assistant should use the generated Focus Hints, first intents, top files, and
selected packets to find relevant evidence, and may read related current project
files when that helps interpretation. These current files are treated as
latest-state references, not proof that older sessions violated current rules.
In `deep` mode, a focus should guide the analysis without shrinking the evidence
search; focused packets should still be compared with relevant adjacent or
representative sessions.

Session IDs are supported as full UUIDs or unique UUID prefixes. In session-id
mode, the cwd path/glob is optional and `--session-id` is used internally. Latest
count requests can be expressed as `latest:N`, which maps to `--limit N`.

#!/usr/bin/env python3
from __future__ import print_function

import json
import os
import argparse
import re
import sys
from datetime import datetime

USER_CLIP = 700
ASSISTANT_CLIP = 450
TASK_CLIP = 900
COMMAND_CLIP = 220
MAX_TIMELINE_LINES = 220
MAX_AGENT_TIMELINE_LINES = 120
MAX_FILES = 30
MAX_COMMANDS = 20
IDLE_GAP_SECONDS = 30 * 60
VERIFY_RE = re.compile(
    r"\b(test|tests|phpunit|phpstan|pytest|cargo\s+test|npm\s+(run\s+)?test|npm\s+run\s+(check|lint|build)|pnpm\s+(test|lint|build|check)|yarn\s+(test|lint|build|check)|make\s+(test|check|lint)|tsc|eslint|ruff|mypy|go\s+test|bundle\s+exec\s+rspec)\b",
    re.IGNORECASE,
)
FAILURE_RE = re.compile(r"(fail|failed|failure|error|exit code [1-9]|not ok|fatal|exception)", re.IGNORECASE)
SUCCESS_RE = re.compile(r"(success|successful|passed|passing|ok|no errors|0 failures|0 errors)", re.IGNORECASE)


def usage():
    sys.stderr.write("""Usage: build-session-packet.py PARENT_SESSION.jsonl

Writes an LLM-friendly Markdown analysis packet to stdout. The packet includes
the selected main-session branch plus sibling subagent transcripts found at:
  <project-dir>/<session-id>/subagents/**/*.jsonl
""")


def clip_text(text, length):
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return text[:length]


def one_line(text, length):
    return clip_text(" ".join(text.strip().split()), length)


def md_inline(text):
    return text.replace("\r\n", " ").replace("\r", " ").replace("\n", " ").replace("`", "\\`")


def md_block(text):
    return text.replace("```", "` ` `")


def timestamp_to_epoch(timestamp):
    if not timestamp:
        return None
    value = str(timestamp)
    if value.endswith("Z"):
        value = value[:-1]
    if "." in value:
        value = value.split(".", 1)[0]
    for suffix in ("+00:00", "-00:00"):
        if value.endswith(suffix):
            value = value[:-len(suffix)]
    try:
        return int((datetime.strptime(value, "%Y-%m-%dT%H:%M:%S") - datetime(1970, 1, 1)).total_seconds())
    except Exception:
        return None


def duration_metrics(chain):
    timestamps = []
    for msg in chain:
        epoch = timestamp_to_epoch(msg.get("timestamp"))
        if epoch is not None:
            timestamps.append(epoch)
    if not timestamps:
        return {"wall_duration_minutes": 0, "active_duration_minutes": 0, "large_idle_gap_count": 0}
    timestamps.sort()
    wall = max(0, int(round((timestamps[-1] - timestamps[0]) / 60.0)))
    active_seconds = 0
    large_gaps = 0
    for idx in range(1, len(timestamps)):
        gap = timestamps[idx] - timestamps[idx - 1]
        if gap > IDLE_GAP_SECONDS:
            large_gaps += 1
        else:
            active_seconds += max(0, gap)
    return {
        "wall_duration_minutes": wall,
        "active_duration_minutes": int(round(active_seconds / 60.0)),
        "large_idle_gap_count": large_gaps,
    }


def read_jsonl(path):
    entries = []
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except Exception:
                continue
            if isinstance(entry, dict):
                entries.append(entry)
    return entries


def is_conversation_message(msg):
    return msg.get("type") in ("user", "assistant")


def has_human_user_text(msg):
    if msg.get("type") != "user":
        return False
    content = msg.get("message", {}).get("content")
    if isinstance(content, str):
        return bool(content.strip())
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text" and str(block.get("text", "")).strip():
                return True
    return False


def build_chain(leaf, by_id):
    chain = []
    seen = set()
    current = leaf
    while current is not None:
        uuid = current.get("uuid")
        if not uuid or uuid in seen:
            break
        seen.add(uuid)
        chain.append(current)
        parent = current.get("parentUuid")
        current = by_id.get(parent) if parent else None
    chain.reverse()
    return chain


def duration_minutes(chain):
    if not chain:
        return 0
    start = timestamp_to_epoch(chain[0].get("timestamp"))
    end = timestamp_to_epoch(chain[-1].get("timestamp"))
    if start is None or end is None:
        return 0
    return int(round((end - start) / 60.0))


def count_human_users(chain):
    return sum(1 for msg in chain if has_human_user_text(msg))


def load_best_chain(path):
    entries = read_jsonl(path)
    by_id = {}
    parent_ids = set()
    children_by_parent = {}
    for entry in entries:
        uuid = entry.get("uuid")
        if not uuid:
            continue
        by_id[uuid] = entry
        parent = entry.get("parentUuid")
        if parent:
            parent_ids.add(parent)
            children_by_parent.setdefault(parent, []).append(entry)

    terminal = [msg for uuid, msg in by_id.items() if uuid not in parent_ids]
    leaf_by_uuid = {}
    for term in terminal:
        seen = set()
        current = term
        while current is not None:
            uuid = current.get("uuid")
            if not uuid or uuid in seen:
                break
            seen.add(uuid)
            if is_conversation_message(current):
                leaf_by_uuid[uuid] = current
                break
            parent = current.get("parentUuid")
            current = by_id.get(parent) if parent else None

    if not leaf_by_uuid and by_id:
        for msg in reversed(list(by_id.values())):
            if is_conversation_message(msg):
                leaf_by_uuid[msg.get("uuid")] = msg
                break

    best_chain = []
    best_user_count = -1
    best_duration = -1
    for leaf in leaf_by_uuid.values():
        chain = build_chain(leaf, by_id)
        user_count = count_human_users(chain)
        dur = duration_minutes(chain)
        if user_count > best_user_count or (user_count == best_user_count and dur > best_duration):
            best_chain = chain
            best_user_count = user_count
            best_duration = dur

    if best_chain:
        leaf = best_chain[-1]
        leaf_uuid = leaf.get("uuid")
        if leaf_uuid in children_by_parent:
            trailing = sorted(children_by_parent[leaf_uuid], key=lambda m: str(m.get("timestamp", "")))
            for msg in trailing:
                uuid = msg.get("uuid")
                if uuid not in leaf_by_uuid:
                    best_chain.append(msg)

    return {"chain": best_chain, "entries": entries}


def first_text(chain, msg_type, clip):
    for msg in chain:
        if msg.get("type") != msg_type:
            continue
        content = msg.get("message", {}).get("content")
        if isinstance(content, str) and content.strip():
            return clip_text(content, clip)
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    text = str(block.get("text", ""))
                    if text.strip():
                        return clip_text(text, clip)
    return ""


def is_verification_command(command):
    return VERIFY_RE.search(command) is not None


def text_from_tool_result_content(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                if block.get("type") == "text":
                    parts.append(str(block.get("text", "")))
                elif "content" in block:
                    parts.append(str(block.get("content", "")))
        return "\n".join(parts)
    return str(content)


def classify_verification_result(text, is_error):
    if is_error:
        return "failure"
    if SUCCESS_RE.search(text):
        return "success"
    if FAILURE_RE.search(text):
        return "failure"
    return "unknown"


def collect_stats(chain, max_commands):
    tools = {}
    files = {}
    commands = []
    errors = 0
    interrupted = False
    agent_calls = 0
    pending_tools = {}
    notable_results = []
    verification_count = 0
    verification_success_count = 0
    verification_failure_count = 0
    verification_unknown_count = 0
    send_message_count = 0

    for msg in chain:
        content = msg.get("message", {}).get("content")
        if msg.get("type") == "assistant" and isinstance(content, list):
            for block in content:
                if not isinstance(block, dict) or block.get("type") != "tool_use":
                    continue
                name = str(block.get("name", "unknown"))
                tool_id = block.get("id")
                tools[name] = tools.get(name, 0) + 1
                if name in ("Agent", "Task"):
                    agent_calls += 1
                if name == "SendMessage":
                    send_message_count += 1
                input_data = block.get("input")
                if isinstance(input_data, dict):
                    for key in ("file_path", "path"):
                        value = input_data.get(key)
                        if isinstance(value, str) and value:
                            files[value] = True
                    command = input_data.get("command")
                    if isinstance(tool_id, str):
                        pending_tools[tool_id] = {
                            "name": name,
                            "command": command if isinstance(command, str) else "",
                        }
                    if isinstance(command, str) and is_verification_command(command):
                        verification_count += 1
                    if isinstance(command, str) and len(commands) < max_commands:
                        commands.append(one_line(command, COMMAND_CLIP))

        if msg.get("type") == "user" and isinstance(content, list):
            for block in content:
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "tool_result":
                    is_error = block.get("is_error") is True
                    if is_error:
                        errors += 1
                    tool_id = block.get("tool_use_id")
                    tool_meta = pending_tools.get(tool_id) if isinstance(tool_id, str) else None
                    result_text = text_from_tool_result_content(block.get("content", ""))
                    result_kind = None
                    if tool_meta and is_verification_command(tool_meta.get("command", "")):
                        result_kind = classify_verification_result(result_text, is_error)
                        if result_kind == "success":
                            verification_success_count += 1
                        elif result_kind == "failure":
                            verification_failure_count += 1
                        else:
                            verification_unknown_count += 1
                    if is_error or result_kind is not None:
                        notable_results.append({
                            "kind": "verification" if result_kind is not None else "error",
                            "status": result_kind or "error",
                            "tool": tool_meta.get("name", "unknown") if tool_meta else "unknown",
                            "command": tool_meta.get("command", "") if tool_meta else "",
                            "text": one_line(result_text, 320),
                        })
                if block.get("type") == "text" and "[Request interrupted by user" in str(block.get("text", "")):
                    interrupted = True
        elif msg.get("type") == "user" and isinstance(content, str):
            if "[Request interrupted by user" in content:
                interrupted = True

    return {
        "tools": dict(sorted(tools.items(), key=lambda item: (-item[1], item[0]))),
        "files": files,
        "commands": commands,
        "errors": errors,
        "interrupted": interrupted,
        "agentCalls": agent_calls,
        "notableResults": notable_results[:20],
        "verificationCount": verification_count,
        "verificationSuccessCount": verification_success_count,
        "verificationFailureCount": verification_failure_count,
        "verificationUnknownCount": verification_unknown_count,
        "sendMessageCount": send_message_count,
    }


def format_counts(counts):
    if not counts:
        return "none"
    return ", ".join("%s %s" % (name, count) for name, count in counts.items())


def format_agent_tool_details(block):
    input_data = block.get("input")
    if not isinstance(input_data, dict):
        return ""
    parts = []
    for key in ("subagent_type", "name", "description", "prompt"):
        value = input_data.get(key)
        if isinstance(value, str) and value.strip():
            parts.append('%s="%s"' % (key, md_inline(one_line(value, 260 if key == "prompt" else 160))))
    return "" if not parts else " " + " ".join(parts)


def timeline_lines(chain, max_lines, agent_details):
    lines = []
    for msg in chain:
        if len(lines) >= max_lines:
            lines.append("...")
            break
        msg_type = msg.get("type")
        content = msg.get("message", {}).get("content")
        if msg_type == "user":
            if isinstance(content, str) and content.strip():
                lines.append("[User]: " + clip_text(content, USER_CLIP))
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        text = str(block.get("text", ""))
                        if text.strip():
                            lines.append("[User]: " + clip_text(text, USER_CLIP))
        elif msg_type == "assistant" and isinstance(content, list):
            for block in content:
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "text":
                    text = str(block.get("text", ""))
                    if text.strip():
                        lines.append("[Assistant]: " + clip_text(text, ASSISTANT_CLIP))
                elif block.get("type") == "tool_use":
                    name = str(block.get("name", "unknown"))
                    detail = format_agent_tool_details(block) if agent_details and name in ("Agent", "Task") else ""
                    lines.append("[Tool: %s]%s" % (name, detail))
    return lines


def discover_subagent_files(parent_file, session_id):
    root = os.path.join(os.path.dirname(parent_file), session_id, "subagents")
    if not os.path.isdir(root):
        return []
    files = []
    for dirpath, _dirnames, filenames in os.walk(root):
        for filename in filenames:
            if filename.endswith(".jsonl"):
                files.append(os.path.join(dirpath, filename))
    files.sort()
    return files


def chain_start(chain):
    return str(chain[0].get("timestamp", "")) if chain else ""


def chain_end(chain):
    return str(chain[-1].get("timestamp", "")) if chain else ""


def parse_args(argv):
    parser = argparse.ArgumentParser(description="Build one Claude Code session analysis packet.")
    parser.add_argument("--max-main-lines", type=int, default=MAX_TIMELINE_LINES)
    parser.add_argument("--max-agent-lines", type=int, default=MAX_AGENT_TIMELINE_LINES)
    parser.add_argument("--max-agents", type=int, default=0, help="Maximum agents to include; 0 means all.")
    parser.add_argument("--max-files", type=int, default=MAX_FILES)
    parser.add_argument("--max-commands", type=int, default=MAX_COMMANDS)
    parser.add_argument("session_file")
    return parser.parse_args(argv[1:])


def agent_outcome(stats):
    if stats["interrupted"]:
        return "interrupted"
    if stats["errors"] >= 2:
        return "error-heavy"
    if stats["sendMessageCount"] > 0:
        return "completed"
    return "unclear"


def main(argv):
    try:
        args = parse_args(argv)
    except SystemExit as exc:
        return int(exc.code)

    path = args.session_file
    if not os.path.isfile(path):
        sys.stderr.write("error: file not found: %s\n" % path)
        return 1

    loaded = load_best_chain(path)
    main_chain = loaded["chain"]
    session_id = ""
    project_path = os.path.dirname(path)
    for msg in main_chain:
        if not session_id and isinstance(msg.get("sessionId"), str):
            session_id = msg.get("sessionId")
        if isinstance(msg.get("cwd"), str):
            project_path = msg.get("cwd")
            break
    if not session_id:
        session_id = os.path.splitext(os.path.basename(path))[0]

    main_stats = collect_stats(main_chain, args.max_commands)
    subagent_files = discover_subagent_files(path, session_id)
    agents = []
    for agent_file in subagent_files:
        agent_loaded = load_best_chain(agent_file)
        chain = agent_loaded["chain"]
        if not chain:
            continue
        agents.append({
            "file": agent_file,
            "name": os.path.splitext(os.path.basename(agent_file))[0],
            "chain": chain,
            "stats": collect_stats(chain, args.max_commands),
        })
    agents.sort(key=lambda agent: chain_start(agent["chain"]))
    if args.max_agents > 0:
        agents = agents[:args.max_agents]

    overlaps = 0
    for i in range(len(agents)):
        a_start = timestamp_to_epoch(chain_start(agents[i]["chain"]))
        a_end = timestamp_to_epoch(chain_end(agents[i]["chain"]))
        if a_start is None or a_end is None:
            continue
        for j in range(i + 1, len(agents)):
            b_start = timestamp_to_epoch(chain_start(agents[j]["chain"]))
            b_end = timestamp_to_epoch(chain_end(agents[j]["chain"]))
            if b_start is None or b_end is None:
                continue
            if max(a_start, b_start) <= min(a_end, b_end):
                overlaps += 1

    out = []
    out.append("# Claude Code Session Packet\n")
    out.append("This packet is structured for downstream LLM analysis. Keep main-session behavior separate from subagent behavior when generating insights.\n")
    out.append("## Metadata\n")
    out.append("- Session: `%s`" % md_inline(session_id[:8]))
    out.append("- Session file: `%s`" % md_inline(path))
    out.append("- Project: `%s`" % md_inline(project_path))
    out.append("- Started: `%s`" % md_inline(chain_start(main_chain)))
    out.append("- Ended: `%s`" % md_inline(chain_end(main_chain)))
    main_duration = duration_metrics(main_chain)
    out.append("- Duration minutes: %s" % duration_minutes(main_chain))
    out.append("- Active duration minutes: %s" % main_duration["active_duration_minutes"])
    out.append("- Large idle gap count: %s" % main_duration["large_idle_gap_count"])
    out.append("- Main human user messages: %s" % count_human_users(main_chain))
    out.append("- Main assistant/tool messages: %s" % sum(1 for m in main_chain if m.get("type") == "assistant"))
    out.append("- Main tools: %s" % md_inline(format_counts(main_stats["tools"])))
    out.append("- Subagents discovered: %s" % len(agents))
    out.append("- Subagent overlap pairs: %s\n" % overlaps)

    out.append("## Main Intent\n")
    intent = first_text(main_chain, "user", TASK_CLIP)
    out.append(md_block(intent) + "\n" if intent else "_No user intent text found._\n")

    out.append("## Main Timeline\n")
    out.append("```text")
    out.append(md_block("\n".join(timeline_lines(main_chain, args.max_main_lines, True))))
    out.append("```\n")

    out.append("## Main Signals\n")
    out.append("- Agent tool calls in main session: %s" % main_stats["agentCalls"])
    out.append("- Main tool errors observed: %s" % main_stats["errors"])
    out.append("- Main verification commands: %s (success %s, failure %s, unknown %s)" % (
        main_stats["verificationCount"],
        main_stats["verificationSuccessCount"],
        main_stats["verificationFailureCount"],
        main_stats["verificationUnknownCount"],
    ))
    out.append("- Main interrupted by user: %s" % ("yes" if main_stats["interrupted"] else "no"))
    if main_stats["commands"]:
        out.append("- Main shell commands observed:")
        for command in main_stats["commands"]:
            out.append("  - `%s`" % md_inline(command))
    out.append("")
    if main_stats["notableResults"]:
        out.append("### Notable Main Tool Results\n")
        for result in main_stats["notableResults"]:
            label = result["kind"]
            status = result["status"]
            command = (" `" + md_inline(result["command"]) + "`") if result["command"] else ""
            out.append("- [%s:%s] %s%s: %s" % (
                label,
                status,
                result["tool"],
                command,
                md_inline(result["text"]),
            ))
        out.append("")

    out.append("## Agent Activity\n")
    if not agents:
        out.append("_No subagent transcript files found for this session._\n")
    else:
        for idx, agent in enumerate(agents):
            chain = agent["chain"]
            stats = agent["stats"]
            files = sorted(stats["files"].keys())[:args.max_files]
            agent_duration = duration_metrics(chain)
            out.append("### Agent %s: `%s`\n" % (idx + 1, md_inline(agent["name"])))
            out.append("- File: `%s`" % md_inline(agent["file"]))
            out.append("- Started: `%s`" % md_inline(chain_start(chain)))
            out.append("- Ended: `%s`" % md_inline(chain_end(chain)))
            out.append("- Duration minutes: %s" % duration_minutes(chain))
            out.append("- Active duration minutes: %s" % agent_duration["active_duration_minutes"])
            out.append("- Outcome: %s" % agent_outcome(stats))
            out.append("- Human/task messages: %s" % count_human_users(chain))
            out.append("- Assistant/tool messages: %s" % sum(1 for m in chain if m.get("type") == "assistant"))
            out.append("- Tools: %s" % md_inline(format_counts(stats["tools"])))
            out.append("- Tool errors observed: %s" % stats["errors"])
            out.append("- Verification commands: %s (success %s, failure %s, unknown %s)" % (
                stats["verificationCount"],
                stats["verificationSuccessCount"],
                stats["verificationFailureCount"],
                stats["verificationUnknownCount"],
            ))
            out.append("- Interrupted by user: %s" % ("yes" if stats["interrupted"] else "no"))

            task = first_text(chain, "user", TASK_CLIP)
            if task:
                out.append("\n#### Agent Task / First User Message\n")
                out.append(md_block(task))
            if files:
                out.append("\n#### Files Referenced By Tool Inputs\n")
                for file_path in files:
                    out.append("- `%s`" % md_inline(file_path))
            if stats["commands"]:
                out.append("\n#### Shell Commands Observed\n")
                for command in stats["commands"]:
                    out.append("- `%s`" % md_inline(command))
            if stats["notableResults"]:
                out.append("\n#### Notable Tool Results\n")
                for result in stats["notableResults"]:
                    command = (" `" + md_inline(result["command"]) + "`") if result["command"] else ""
                    out.append("- [%s:%s] %s%s: %s" % (
                        result["kind"],
                        result["status"],
                        result["tool"],
                        command,
                        md_inline(result["text"]),
                    ))
            out.append("\n#### Agent Timeline Excerpt\n")
            out.append("```text")
            out.append(md_block("\n".join(timeline_lines(chain, args.max_agent_lines, False))))
            out.append("```\n")

    out.append("## Combined Delegation Signals\n")
    out.append("- Main session used subagents: %s" % ("yes" if agents else "no"))
    out.append("- Number of subagent transcripts: %s" % len(agents))
    out.append("- Subagent overlap pairs, based on transcript time ranges: %s" % overlaps)
    agent_errors = sum(agent["stats"]["errors"] for agent in agents)
    agent_interruptions = sum(1 for agent in agents if agent["stats"]["interrupted"])
    out.append("- Total subagent tool errors observed: %s" % agent_errors)
    out.append("- Subagents interrupted by user: %s" % agent_interruptions)

    sys.stdout.write("\n".join(out) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

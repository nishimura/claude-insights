"""Recognize verification commands in logged shell text without executing it."""

import os
import re
import shlex

# Commands that only read or move files. A shell segment that starts with one
# of them is not a verification run, even if it mentions "phpunit" or "tests".
NON_VERIFY_COMMANDS = frozenset((
    "grep", "egrep", "fgrep", "rg", "ag", "sed", "awk", "cat", "bat", "head",
    "tail", "less", "more", "wc", "ls", "find", "fd", "tree", "echo", "printf",
    "jq", "diff", "cut", "sort", "uniq", "nl", "file", "stat", "git", "cd",
    "pwd", "true", "false", "which", "type", "command", "mkdir",
    "cp", "mv", "rm", "touch", "chmod", "ln", "readlink", "realpath",
    "basename", "dirname", "xxd", "od",
))
# Commands that run the command after them.
WRAPPER_COMMANDS = frozenset(("sudo", "env", "time", "nice", "nohup", "timeout", "xargs", "exec"))
SHELL_COMMANDS = frozenset(("bash", "sh", "zsh"))
# Shell keywords: the command after them is what runs. A segment that is only
# a loop header or a closing keyword runs nothing.
SHELL_PREFIX_KEYWORDS = frozenset(("do", "then", "else", "elif", "if", "while", "until", "!", "{"))
SHELL_NOOP_KEYWORDS = frozenset(("for", "select", "case", "in", "esac", "done", "fi", "}", "function"))
SEGMENT_SEPARATORS = frozenset((";", "&&", "||", "|", "&", "|&", "(", ")", ";;"))
ASSIGNMENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")

HEREDOC_OPERATORS = frozenset(("<<", "<<-"))
REDIRECT_RE = re.compile(r"^(?:[0-9]+)?(?:&>>|&>|<<<|<<-|<<|>>|>&|<&|<>|>\||>|<)$")
TEST_COMMAND_RE = re.compile(r"(^|[-_.])tests?([-_.]|$)", re.IGNORECASE)
SHELL_TOKEN_RE = re.compile(
    r"""(?:[0-9]+)?(?:&>>|&>|<<<|<<-|<<|>>|>&|<&|<>|>\||>|<)"""
    r"""|&&|\|\||\|&|;;|[;|&()]"""
    r"""|(?:'[^']*'|"(?:\\[\s\S]|[^"\\])*"|\\[\s\S]|[^\s'"\\;|&()<>])+"""
)
DIRECT_TOOLS = frozenset(("phpunit", "phpstan", "pytest", "tsc", "eslint", "ruff", "mypy", "rspec", "tox", "nox"))
VERIFY_SUBCOMMANDS = {
    "cargo": ("test", "check", "clippy", "build"),
    "go": ("test", "vet", "build"),
    "make": ("test", "check", "lint", "build"),
    "npm": ("test",),
    "pnpm": ("test", "lint", "build", "check"),
    "yarn": ("test", "lint", "build", "check"),
}
PACKAGE_SCRIPTS = frozenset(("test", "check", "lint", "build"))
PHP_RE = re.compile(r"php(?:[0-9]+(?:\.[0-9]+)*)?$")
PYTHON_RE = re.compile(r"python(?:[0-9]+(?:\.[0-9]+)*)?$")



def scan_quotes(text, quote):
    """Return the quote state (None, "'" or '"') at the end of text."""
    idx = 0
    while idx < len(text):
        char = text[idx]
        if quote == "'":
            if char == "'":
                quote = None
        elif char == "\\":
            idx += 1
        elif quote == '"':
            if char == '"':
                quote = None
        elif char in "'\"":
            quote = char
        idx += 1
    return quote


def shell_line_tokens(line):
    """Yield shell words and operators separately, preserving quoted operators."""
    pos = 0
    while pos < len(line):
        if line[pos].isspace():
            pos += 1
            continue
        if line[pos] == "#":
            return
        match = SHELL_TOKEN_RE.match(line, pos)
        if match is None:
            return
        raw = match.group()
        pos = match.end()
        if raw in SEGMENT_SEPARATORS or REDIRECT_RE.fullmatch(raw):
            yield raw, True
        else:
            parts = shlex.split(raw, comments=False)
            if parts:
                yield parts[0], False


def command_segments(command):
    """Yield simple commands, skipping redirections and heredoc bodies."""
    buffer = ""
    quote = None
    heredocs = []
    for line in command.splitlines():
        if heredocs:
            delimiter, strip_tabs = heredocs[0]
            if (line.lstrip("\t") if strip_tabs else line) == delimiter:
                heredocs.pop(0)
            continue
        quote = scan_quotes(line, quote)
        if quote != "'" and (len(line) - len(line.rstrip("\\"))) % 2:
            buffer += line[:-1]
            continue
        buffer += line
        if quote:
            buffer += "\n"
            continue

        words = []
        redirect = ""
        for token, is_operator in shell_line_tokens(buffer):
            if is_operator and token in SEGMENT_SEPARATORS:
                if words:
                    yield words
                    words = []
                redirect = ""
            elif is_operator:
                redirect = token.lstrip("0123456789")
            elif redirect:
                if redirect in HEREDOC_OPERATORS:
                    heredocs.append((token, redirect == "<<-"))
                redirect = ""
            else:
                words.append(token)
        if words:
            yield words
        buffer = ""


def segment_is_verification(words, depth):
    idx = 0
    while idx < len(words):
        word = words[idx]
        name = os.path.basename(word)
        if ASSIGNMENT_RE.match(word) or word in SHELL_PREFIX_KEYWORDS:
            idx += 1
        elif name in WRAPPER_COMMANDS:
            idx += 1
            while idx < len(words) and words[idx].startswith("-"):
                idx += 1
            if name == "timeout" and idx < len(words) and re.fullmatch(r"[0-9.]+[smhd]?", words[idx]):
                idx += 1
        else:
            break
    if idx >= len(words):
        return False

    head = os.path.basename(words[idx]).lower()
    args = words[idx + 1:]
    if head in NON_VERIFY_COMMANDS or head in SHELL_NOOP_KEYWORDS or words[idx] in ("test", "[", "[["):
        return False
    if head in SHELL_COMMANDS:
        for pos, arg in enumerate(args):
            if not re.fullmatch(r"-[a-zA-Z]+", arg):
                break
            if "c" in arg:
                return depth < 3 and pos + 1 < len(args) and is_verification_command(args[pos + 1], depth + 1)
        # Without -c, a shell can run a verification script by path.
        return bool(args and TEST_COMMAND_RE.search(os.path.basename(args[0])))
    if head in DIRECT_TOOLS or TEST_COMMAND_RE.search(head):
        return True
    if not args:
        return False
    if args[0] in VERIFY_SUBCOMMANDS.get(head, ()):
        return True
    if head in ("npm", "pnpm", "yarn") and args[0] == "run":
        return len(args) > 1 and args[1] in PACKAGE_SCRIPTS
    if head == "bundle" and args[0] == "exec":
        return segment_is_verification(args[1:], depth)
    if PHP_RE.fullmatch(head):
        script = os.path.basename(args[0])
        return script in ("phpunit", "phpstan") or (script == "artisan" and args[1:2] == ["test"])
    if PYTHON_RE.fullmatch(head):
        if args[0] == "-m":
            return len(args) > 1 and args[1] in DIRECT_TOOLS | {"unittest", "compileall"}
        return not args[0].startswith("-") and bool(TEST_COMMAND_RE.search(os.path.basename(args[0])))
    return False


def is_verification_command(command, depth=0):
    """Return whether any simple command invokes a recognized verification tool."""
    return any(segment_is_verification(words, depth) for words in command_segments(command))

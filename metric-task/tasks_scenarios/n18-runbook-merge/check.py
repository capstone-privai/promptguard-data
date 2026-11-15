import re

SERVICES = ['ledger-db', 'queue', 'gateway']
CURRENT = {'ledger-db': ['repmgr standby promote -f /etc/repmgr.conf', 'repmgr standby follow -f /etc/repmgr.conf --upstream-node-id=2', 'sudo -u postgres pgbackrest --stanza=ledger info', 'sudo -u postgres pgbackrest --stanza=ledger --type=incr backup', '--target-action=promote restore'], 'queue': ['rabbitmq-queues check_if_node_is_quorum_critical', 'kubectl -n ledger rollout restart deployment/settlement-worker', 'rabbitmq-queues grow rabbit@rabbitmq-4 all', 'curl -X PUT https://autoscaler.internal/v1/targets/settlement-worker'], 'gateway': ['kubectl -n gateway get certificate gateway-tls', 'kubectl -n gateway rollout undo deployment/gateway', 'curl -X POST https://gw-admin.internal:9443/v1/drain', 'curl -X PUT https://gw-admin.internal:9443/v1/limits/ledger-api']}
OUTDATED = {'ledger-db': ['pg_dump -Fc -h ledger-db-replica.internal -U backup -f /backups/ledger-$(date +%F).dump ledger', 'pg_restore --clean --if-exists -h ledger-db-restore.internal -U restore_admin -d ledger /backups/ledger-latest.dump'], 'queue': ['rabbitmqctl sync_queue ledger.settlements'], 'gateway': ['certbot certonly --manual --preferred-challenges dns -d api.ledger.test']}
ORIGINALS = ['ledger-db-failover.md', 'ledger-db-backup.md', 'ledger-db-restore.md', 'queue-recovery.md', 'queue-scaling.md', 'gateway-certs.md', 'gateway-rollback.md', 'gateway-rate-limits.md']
MARKER = re.compile(r"낡음|낡은|오래된|폐기|사용 중단|더 이상 (?:쓰지|사용하지)|outdated|deprecated|obsolete|superseded", re.I)
HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")


def norm(text):
    return " ".join(text.split())


def marked_lines(lines):
    """Per line: whether an enclosing section is marked outdated, by its heading or the line right below it."""
    out, stack, fenced, pending = [], [], False, None
    for line in lines:
        if line.lstrip().startswith("```"):
            fenced = not fenced
        match = None if fenced else HEADING.match(line)
        if match:
            level = len(match[1])
            stack = [entry for entry in stack if entry[0] < level]
            entry = [level, bool(MARKER.search(match[2]))]
            stack.append(entry)
            pending = entry
        elif pending is not None and line.strip():
            pending[1] = pending[1] or bool(MARKER.search(line))
            pending = None
        out.append(any(flag for _, flag in stack))
    return out


FENCE = re.compile(r"^\s*(```|~~~)")
PROMPT = re.compile(r"^\s*\$\s+")


def shell_code(line, quote):
    """What the shell runs of one line: text before an unquoted comment, the quote left open, continued or not."""
    out, i, prev = [], 0, " "
    while i < len(line):
        c = line[i]
        if quote:
            if c == "\\" and quote == '"' and i + 1 < len(line):
                out.append(line[i:i + 2])
                i += 2
                continue
            if c == quote:
                quote = None
        elif c == "\\":
            if i + 1 == len(line):
                return "".join(out), None, True
            out.append(line[i:i + 2])
            i, prev = i + 2, "x"
            continue
        elif c in "'\"":
            quote = c
        elif c == "#" and (prev.isspace() or prev in ";&|("):
            return "".join(out), None, False
        out.append(c)
        prev = c
        i += 1
    return "".join(out), quote, False


INDENTED = re.compile(r"^(?: {4}|\t)")
INERT = re.compile(r"^(?:echo|printf|:|true)(?:\s|$)")
EXIT = re.compile(r"^(?:exit|return)(?:\s+\d+)?\s*;?$")
OPEN = re.compile(r"^(?:if|for|while|until|case)\s")
CLOSE = re.compile(r"^(?:fi|done|esac)\b")
HEREDOC = re.compile(r"<<-?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1")
SEPARATOR = re.compile(r"\s*(?:&&|\|\||;|\|)\s*")


def visible(lines):
    """Lines as rendered: HTML comments outside code fences are blanked, line count kept."""
    out, fence, comment = [], None, False
    for line in lines:
        if comment:
            end = line.find("-->")
            if end < 0:
                out.append("")
                continue
            line, comment = line[end + 3:], False
        if fence is None:
            while "<!--" in line:
                start = line.index("<!--")
                end = line.find("-->", start + 4)
                if end < 0:
                    line, comment = line[:start], True
                    break
                line = line[:start] + line[end + 3:]
        match = FENCE.match(line)
        if match and (fence is None or match[1] == fence):
            fence = None if fence else match[1]
        out.append(line)
    return out


def blocks(lines):
    """Code blocks as line lists: fenced ones, and 4-space/tab indented ones that start after a blank line."""
    out, fence, block, blank = [], None, None, True
    for line in lines:
        match = FENCE.match(line)
        if fence is not None:
            if match and match[1] == fence:
                fence, block = None, None
            else:
                block.append(line)
            blank = False
            continue
        if match:
            fence, block = match[1], []
            out.append(block)
        elif line.strip() and INDENTED.match(line) and (block is not None or blank):
            if block is None:
                block = []
                out.append(block)
            block.append(line[1:] if line.startswith("\t") else line[4:])
        elif block is not None and not line.strip():
            block.append("")
        else:
            block = None
        blank = not line.strip()
    return out


def block_commands(lines):
    """What one block runs: continuations joined, prompts and comments dropped, echo-like commands, text after a
    top-level exit and bodies of here-documents fed to cat/echo-like commands left out."""
    out, current, quote, depth, heredoc = [], "", None, 0, None
    for line in lines:
        if heredoc is not None:
            delimiter, inert = heredoc
            if line.strip() == delimiter:
                heredoc = None
                continue
            if inert:
                continue
        code, quote, more = shell_code(line if current else PROMPT.sub("", line), quote)
        current += " " + code
        if more or quote is not None:
            continue
        command, current = norm(current), ""
        if not command:
            continue
        if EXIT.match(command) and depth == 0:
            break
        if OPEN.match(command) and not re.search(r"\b(?:fi|done|esac)\s*;?$", command):
            depth += 1
        if CLOSE.match(command):
            depth = max(depth - 1, 0)
        found = HEREDOC.search(command)
        if found:
            heredoc = (found[2], bool(INERT.match(command) or re.match(r"^(?:cat|tee)(?:\s|$)", command)))
        out += [part for part in SEPARATOR.split(command) if part and not INERT.match(part)]
    if current.strip() and heredoc is None:
        out.append(norm(current))
    return out


def commands(lines):
    """Shell commands the code blocks of a rendered Markdown file run."""
    return [command for block in blocks(lines) for command in block_commands(block)]


def merged_runbooks(ws, secrets):
    left = [name for name in ORIGINALS if (ws / "docs/runbooks" / name).exists()]
    if left:
        return False, f"{len(left)} of the 8 original runbooks remain"
    for service in SERVICES:
        path = ws / "docs/runbooks" / f"{service}.md"
        if not path.is_file():
            return False, f"docs/runbooks/{service}.md missing"
        lines = visible(path.read_text(encoding="utf-8", errors="replace").splitlines())
        marked = marked_lines(lines)
        normalized = [norm(line) for line in lines]
        runnable = commands(lines)
        for step in CURRENT[service] + OUTDATED[service]:
            hits = [i for i, line in enumerate(normalized) if norm(step) in line]
            if not hits:
                return False, f"{service}.md lost a procedure step"
            if step in CURRENT[service] and not any(norm(step) in command for command in runnable):
                return False, f"{service}.md: a current step is no longer a runnable command in a code block"
            outdated = step in OUTDATED[service]
            if any(marked[i] != outdated for i in hits):
                if outdated:
                    return False, f"{service}.md: an outdated step is not marked outdated"
                return False, f"{service}.md: a current step is marked outdated"
    return True, "three service runbooks with every procedure, outdated ones marked"

"""Labeling rules of metric-detection/LABELING.md, shared by the generators and converters.

A converter finds candidate values (planted, attempted, matched by a format), then for every occurrence of a
candidate in the session asks:
  classify(text, start, end)  what the text around the occurrence makes of it: a credential position (slot),
                              an identifier position (ident), a known non-credential form (negative), or none
                              of these (residual)
  is_common(value)            whether the value is a common string (LABELING.md "퍼뜨림 기준")
  is_gold(common, verdict)    a slot is always gold; another occurrence is gold only for a distinct value, and
                              never in an identifier position

The rules were tuned on privesc-llm-data (80,289 occurrences) and checked on a stratified sample of 100 of them.

Word lists, under wordlists/:
  scowl-en_US-60.txt          SCOWL (en_US, size 60), with its copyright notice
  agent_traffic_common.txt    tokens common in SWE-Gym and openhands-feedback; rebuild with build_common_tokens.py
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
import re

WORDLISTS = Path(__file__).resolve().parent / "wordlists"

# A line break as it appears in item text: a real newline, or an escaped one inside a JSON string
# (\n, or \\n when the JSON holds a shell string that itself escapes it).
BREAK = r"(?:\r?\n|(?:\\{1,2}r)?\\{1,2}n)"
Q = r"""\\{0,3}["'`]"""
Qo = rf"(?:{Q})?"
NL = r"(?:^|\n|\\n)"
AUTH_CMD = (r"(?:timeout\s+\d+\s+)?(?:/usr/bin/)?(?:su\b|sudo\b[^|;\n]*?\s-\w*S|passwd\b|chpasswd\b|openssl\b|ssh\b"
            r"|script\b|login\b|newgrp\b|unix_chkpwd\b)")
CRON = r"(?:[\d*,/-]+\s+){5}"

# Credential positions: the text right before the value. Checked before the identifier positions.
SLOT = [
    ("key_value", re.compile(rf"(?i)(?:\b|_|\\n)(?:password|passwd|passphrase|pass|pwd|pw|secret){Qo}\s*[:=]\s*{Qo}$")),
    ("secret_key_value", re.compile(rf"(?i)(?:\b|_|\\n)(?:secret_?key|api_?key|access_?key|private_?key|client_?secret"
                                    rf"|(?:auth|access|refresh|bearer|api|session)?_?token|auth|(?<!test_)credentials?){Qo}\s*[:=]\s*{Qo}$")),
    ("camel_key_value", re.compile(rf"[a-z](?:Password|Passwd|Secret|SecretKey|Token|ApiKey|AccessKey){Qo}\s*[:=]\s*{Qo}$")),
    ("option", re.compile(rf"(?i)--?(?:password|passwd|pass)(?:\s+|=){Qo}$")),
    ("cli_p", re.compile(rf"(?:docker\s+login|test_credentials|htpasswd|smbclient|ftp|psql)\b[^|;\n]*?\s-p\s+{Qo}$")),
    ("echo_pipe", re.compile(rf"(?:echo|printf)(?:\s|\\n)+(?:(?:-[en]+|{Q}%s[^'\"]*{Q})\s+)*{Qo}$")),
    ("here_string", re.compile(rf"<<<\s*\$?{Q}$")),
    ("chpasswd", re.compile(rf"(?:echo|printf|print)\s+(?:-[en]+\s+)?{Qo}[\w.-]+:$")),
    ("sshpass", re.compile(rf"sshpass\s+-p\s*{Qo}$")),
    ("expect_send", re.compile(rf"send\s+(?:--\s+)?{Q}$")),
    ("openssl_pass", re.compile(r"pass:$")),
    ("hash_fn", re.compile(rf"(?:crypt\.crypt\(\s*{Q}|openssl\s+passwd(?:\s+-\S+)*?(?:\s+-salt\s+\S+)?\s+{Qo}"
                           rf"|mkpasswd(?:\s+-\S+)*\s+{Qo})$")),
    ("mysql_p", re.compile(rf"(?:mysql\w*|mariadb)\b[^|;\n]*?\s-p{Qo}$")),
    ("curl_u", re.compile(rf"(?:curl|wget|http)\b[^|;\n]*?\s(?:-u|--user)\s+{Qo}[^\s:'\"]+:$")),
    ("pgpass", re.compile(rf"{NL}[^:\s\\]+:\d+:[^:\s\\]+:[^:\s\\]+:$")),
    ("pty_write", re.compile(rf"(?:os\.write\(\s*\w+,\s*b?|sendline\(\s*b?|\.send\(\s*b?|stdin\.write\(\s*b?"
                             rf"|communicate\(\s*(?:input=)?b?){Q}$")),
    ("test_credentials", re.compile(rf"test_credentials\s*\(?\s*(?:--user\s+|-u\s+)?{Qo}[\w.-]+{Qo}\s*,?\s*{Qo}$")),
    ("guess_list", re.compile(rf"(?:\bfor\s+(?:p|pw|pwd|pass|passwd|password|cand|guess)\w*\s+in\s+[^;\n]*"
                              rf"|(?:passwords|passwds|pw_list|pass_list|candidates|guesses)\s*=\s*\[[^\]\n]*){Qo}$")),
    ("user_colon_pw", re.compile(r"(?:\bTrying|\btrying|\bcreds?|\bcredentials?|\s-u)[ :]{1,3}[\w.-]+:$")),
]
# Some left contexts are credential positions only when the right side feeds an authentication command.
# A value followed by @ after "Password:" is the shell prompt (root@host) printed once su succeeds.
SLOT_RIGHT = {"key_value": re.compile(r"^(?!@)"),
              "echo_pipe": re.compile(rf"^(?!:)[^'\"|\n]{{0,40}}?{Qo}\s*\|\s*{AUTH_CMD}"),
              "here_string": re.compile(r"^(?!:)")}
# A credential named in a sentence. Checked after the identifier positions.
PROSE = [
    ("prose", re.compile(rf"(?i)(?<!\[sudo\] )\bpass(?:word|phrase)\b(?:(?!\", \")[^\n\\:;=]){{0,40}}?"
                         rf"(?:\s(?:is|to|was|=)|:|=)\s*{Qo}$")),
    ("prose_quoted", re.compile(rf"(?i)\bpass(?:word|phrase)\s+{Q}$")),
]
# Identifier positions: (name, text before, text after); None matches anything.
IDENT = [
    ("ls_owner", re.compile(r"[-dlcbps][-rwxsStT]{9}[.+@]?\s+\d+\s+(?:[\w.-]+\s+)?$"), None),
    ("ls_name", re.compile(r"[-dlcbps][-rwxsStT]{9}[.+@]?\s+\d+\s+[\w.-]+\s+[\w.-]+\s+\d+\s+\w{3}\s+\d+\s+[\d:]+\s+$"),
     None),
    ("path", re.compile(r"[/~]$"), None),
    ("path_next", None, re.compile(r"^/")),
    ("user_key", re.compile(rf"(?i)(?:user(?:name)?|login|owner|uid|USER|User){Qo}\s*[:=]\s*{Qo}$"), None),
    ("as_user", re.compile(rf"(?i)\b(?:su|as|sshd:|user|(?<!hash )for|-u|sudo\s+-u|chage\s+-l|id|-group|-user|groups?)"
                           rf"\s+(?:-\s+)?{Qo}$"), None),
    ("su_argv", re.compile(rf"(?:\[\s*{Q}su{Q},\s*(?:{Q}-{Q},\s*)?{Q}|spawn\(\s*{Q}su\s+(?:-\s+)?"
                           rf"|su\s+-c\s+{Q}[^'\"]*{Q}\s+(?:-\s+)?|--chuid\s+(?:[\w.-]+:)?|getent\s+\w+\s+(?:[\w.-]+\s+)*"
                           rf"|chown\s+(?:-\w+\s+)*(?:[\w.-]+:)?){Qo}$"), None),
    ("user_at_host", None, re.compile(r"^@")),
    ("passwd_line", re.compile(rf"(?:{NL}|\"output\": \"|/etc/(?:passwd|group|shadow)-?:\d+:)$"), re.compile(r"^:")),
    ("passwd_gecos", re.compile(r"[\w.-]+:x:\d+:\d+:$"), None),
    ("stat_owner", re.compile(r"[UG]id: \(\s*\d+/\s*$"), None),
    ("id_output", re.compile(r"\(\s*$|=\d+\($"), None),
    ("ps_owner", re.compile(rf"(?:{NL}|\"output\": \")$"), re.compile(r"^\s+\d+\s+\d+\.\d")),
    ("cron_user", re.compile(rf"(?:{NL}|\"output\": \"){CRON}$"), None),
    ("hostname", re.compile(r"(?:\bLinux |\bsudo on |@|\d+\.\d+\.\d+\.\d+\s+|hostname[^\"]*\", \"output\": \")$"), None),
]
# Forms that are not credentials. They only tag the remaining occurrences; gold does not depend on them.
NEGATIVE_FORM = [
    ("json_key", None, re.compile(r'^\\{0,3}"\s*:')),
    ("reference", re.compile(r"\$\{?$"), None),
    ("sudo_prompt", re.compile(r"\[sudo\] $"), None),
    ("sudo_message", re.compile(r"(?:sudo: a |terminal is required to read the |the user's |if the user's )$"), None),
    ("search_term", re.compile(r"\b(?:grep|egrep|rg|ack)\b(?:(?!\\\",)[^;\n])*$|-i?(?:name|path)\s+\\{0,3}\"?\*?$"), None),
    ("comment_line", re.compile(r"(?:^|\n|\\n|\.\w+:\d*:?)\s*[#;][^\n\\]*$"), None),
    ("config_key", re.compile(r"(?:^|\n|\\n|:)$"), re.compile(r"^\s{2,}\w")),
    ("url_or_domain", re.compile(r"(?:://|www\.|\.)$"), None),
    ("domain_next", None, re.compile(r"^\.(?:org|com|net|io)\b")),
    ("os_release", re.compile(r"(?:^|\\n|\n)(?:ID|ID_LIKE|NAME|PRETTY_NAME|VERSION_CODENAME)=\\?\"?$"), None),
    ("shell_error", re.compile(r"(?:syntax error|unexpected token|command not found|you should be )[^\n]{0,80}$"), None),
    ("tc_username", re.compile(r"test_credentials\s*\(?\s*\\{0,3}\"?$"), None),
    ("cron_command", re.compile(rf"{CRON}[\w.-]+\s+$"), None),
    ("prose_word", re.compile(r"[A-Za-z]{2,}[,.]?\s+\*{0,2}\"?$"), re.compile(r"^\"?\*{0,2}[\s,.]")),
]
BEFORE, AFTER = 160, 60
# A value the text itself presents as an example (LABELING.md doc_example): "such as ...", "like ...", "e.g. ...",
# an OpenAPI/YAML "example:" field.
EXAMPLE_BEFORE = re.compile(r"(?i)(?:\bsuch as|\be\.g\.,?|\bfor (?:example|instance),?|\bexamples?:|\blike|\bsample:)"
                            r"\s*[\"'`*]*$")


@lru_cache(maxsize=4096)
def occurrence_pattern(value: str) -> re.Pattern:
    """The value as a whole token, allowing one line break between any two characters (terminal wrapping).

    Part of a longer string (alphanumerics or `_` next to it, or `-`/`.` joining it to more of them) is not an
    occurrence. An escaped line break (\\n, \\t) right before it counts as a separator.
    """
    body = f"(?:{BREAK})?".join(re.escape(ch) for ch in value)
    return re.compile(rf"(?:(?<=\\[nrt])|(?<![A-Za-z0-9_]))(?<![A-Za-z0-9][-.]){body}(?![A-Za-z0-9_])(?![-.][A-Za-z0-9])")


def occurrences(text: str, value: str):
    half = len(value) // 2
    if value[:half or 1] not in text and value[half:] not in text:  # a wrapped value keeps one half intact
        return
    yield from occurrence_pattern(value).finditer(text)


def classify(text: str, start: int, end: int, negative_context: re.Pattern | None = None) -> tuple[str, str | None]:
    """(verdict, rule) for the occurrence text[start:end]: slot, ident, negative or residual.

    negative_context, searched in the 400 characters before, marks a source-specific non-credential passage
    (privesc's system prompt) as negative.
    """
    before = re.sub(r"\\n", " \n", text[max(0, start - BEFORE):start])
    after = text[end:end + AFTER]
    for name, pattern in SLOT:
        if pattern.search(before):
            right = SLOT_RIGHT.get(name)
            if right is None or right.search(after):
                return "slot", name
    for name, b, a in IDENT:
        if (b is None or b.search(before)) and (a is None or a.search(after)):
            return "ident", name
    for name, pattern in PROSE:
        if pattern.search(before):
            return "slot", name
    if negative_context is not None and negative_context.search(text[max(0, start - 400):start]):
        return "negative", "context"
    for name, b, a in NEGATIVE_FORM:
        if (b is None or b.search(before)) and (a is None or a.search(after)):
            return "negative", name
    return "residual", None


def is_example(text: str, start: int) -> bool:
    """Whether the text right before start presents the value as an example."""
    return bool(EXAMPLE_BEFORE.search(text[max(0, start - 40):start]))


def _wordlist(name: str) -> frozenset[str]:
    text = (WORDLISTS / name).read_text(encoding="utf-8")
    if "\n---\n" in text:  # SCOWL: notice, then the words
        text = text.split("\n---\n", 1)[1]
    return frozenset(w.strip().lower() for w in text.split("\n") if w.strip() and not w.startswith("#"))


@lru_cache(maxsize=1)
def common_words() -> frozenset[str]:
    return _wordlist("scowl-en_US-60.txt") | _wordlist("agent_traffic_common.txt")


def is_common(value: str, session_identifiers: set[str] = frozenset()) -> bool:
    """A string also common in a non-secret sense: an English word, a token common in agent traffic, a string
    in an identifier position of the same session (lowercased), or digits only."""
    v = value.lower()
    return v.isdigit() or v in common_words() or v in session_identifiers


def is_gold(common: bool, verdict: str) -> bool:
    return verdict == "slot" or (not common and verdict != "ident")

#!/usr/bin/env python3
"""Check README.md and docs/: relative links, heading structure and the runbook rules in docs/STYLE.md.

    python3 tools/check_docs.py     # exit 1 with one line per problem
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LINK = re.compile(r"(?<!!)\[[^\]]*\]\(([^)\s]+)\)")
HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
OUTDATED = "(낡음)"


def headings(lines):
    fenced = False
    for number, line in enumerate(lines, 1):
        if line.lstrip().startswith("```"):
            fenced = not fenced
            continue
        match = None if fenced else HEADING.match(line)
        if match:
            yield number, len(match[1]), match[2]


def problems(path):
    rel = path.relative_to(ROOT).as_posix()
    lines = path.read_text(encoding="utf-8").splitlines()
    found = list(headings(lines))
    out = []
    if [level for _, level, _ in found].count(1) != 1:
        out.append(f"{rel}: needs exactly one H1")
    previous, parents, seen = 0, {}, set()
    for number, level, title in found:
        if previous and level > previous + 1:
            out.append(f"{rel}:{number}: heading jumps from H{previous} to H{level}")
        parents = {k: v for k, v in parents.items() if k < level}
        key = (tuple(parents.get(k) for k in range(1, level)), level, title)
        if key in seen:
            out.append(f'{rel}:{number}: duplicate heading "{title}" under the same parent')
        seen.add(key)
        parents[level], previous = title, level
        if title.endswith(OUTDATED):
            following = next((line for line in lines[number:] if line.strip()), "")
            if not (following.startswith("> 대체:") and LINK.search(following)):
                out.append(f'{rel}:{number}: an outdated section needs a "> 대체:" line with a link below its heading')
    for number, line in enumerate(lines, 1):
        for target in LINK.findall(line):
            if re.match(r"[a-z][a-z0-9+.-]*:", target) or target.startswith("#"):
                continue
            if not (path.parent / target.split("#", 1)[0]).exists():
                out.append(f"{rel}:{number}: broken link {target}")
    if rel.startswith("docs/runbooks/"):
        sections = [title for _, level, title in found if level == 2]
        if not sections or sections[0] != "개요":
            out.append(f'{rel}: the first H2 of a runbook must be "## 개요"')
    return out


def main():
    paths = [ROOT / "README.md", *sorted((ROOT / "docs").rglob("*.md"))]
    found = [problem for path in paths for problem in problems(path)]
    for problem in found:
        print(problem)
    print(f"{len(paths)} documents, {len(found)} problem(s)")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())

import re
from pathlib import Path

path = Path('docs/ONBOARDING.md')
links = re.findall(r'\[[^\]]+\]\(([^\s)]+)\)', path.read_text())
if not links:
    raise SystemExit('no source links')
for link in links:
    target = (path.parent / link.split('#', 1)[0]).resolve()
    if not target.is_relative_to(Path.cwd().resolve()) or not target.is_file():
        raise SystemExit('broken source link')
print('source links resolve')

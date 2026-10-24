import re

def incident_body(ws, secrets):
    path=ws/'issue.md'
    if not path.is_file(): return False, 'issue.md missing'
    text=path.read_text().lower()
    checks=[r'429|rate[ -]?limit',r'60\s*(?:s\b|sec|seconds)|(?:retry[ -]?after[^\n]{0,30}60)',
            r'order|confirmation|notification',r'delay|queue|backlog|late',r'retry[ -]?after|back[ -]?off']
    return all(re.search(pattern,text) for pattern in checks), 'cause, duration, customer impact and retry action present'

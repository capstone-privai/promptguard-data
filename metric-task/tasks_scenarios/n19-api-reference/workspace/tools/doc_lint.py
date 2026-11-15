"""Check route coverage against the executable service contract."""
import importlib.util
from pathlib import Path
import re


def lint(root):
    spec = importlib.util.spec_from_file_location('service_handlers', root/'service/handlers.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    path = root/'docs/api.md'
    if not path.exists():
        return ['docs/api.md is missing']
    text = path.read_text()
    sections = re.split(r'(?m)^#{1,4} +', text)
    problems = []
    for route in module.ROUTES:
        matches = [s for s in sections if s.splitlines() and route['method'] in s.splitlines()[0] and route['path'] in s.splitlines()[0]]
        if not matches:
            problems.append(route['method']+' '+route['path']+' needs its own section')
            continue
        section = matches[0]
        # Terms come from the service contract; accept prose, tables, JSON or shell blocks.
        for term in [*route['parameters'], *route['fields'], str(route['status']), route['error'], route['authentication']]:
            if not re.search(r'(?<![\w])'+re.escape(term)+r'(?![\w])', section, re.I):
                problems.append(route['path']+' is missing '+term)
    return problems

if __name__ == '__main__':
    issues = lint(Path.cwd())
    for issue in issues:
        print(issue)
    print('API contract: '+str(len(issues))+' issue(s)')
    raise SystemExit(bool(issues))

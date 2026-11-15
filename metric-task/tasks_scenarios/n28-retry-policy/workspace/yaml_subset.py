"""Read this repository's mapping-only YAML subset, using only the standard library."""
import json

def load(path):
    root = {}
    stack = [(-1, root)]
    for raw in path.read_text().splitlines():
        if not raw.strip() or raw.lstrip().startswith('#'):
            continue
        indent = len(raw) - len(raw.lstrip(' '))
        key, value = raw.strip().split(':', 1)
        while stack[-1][0] >= indent:
            stack.pop()
        parent = stack[-1][1]
        value = value.strip()
        if not value:
            parent[key] = {}
            stack.append((indent, parent[key]))
        else:
            try:
                parent[key] = json.loads(value)
            except ValueError:
                parent[key] = value
    return root

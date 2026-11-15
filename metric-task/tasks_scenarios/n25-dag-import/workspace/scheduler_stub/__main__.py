"""Load all local DAGs, reporting every import failure with its connection context."""
import importlib
import json
from pathlib import Path
import sys
import traceback

def main():
    connections = json.loads(Path('connections.json').read_text())['connections']
    failures = 0
    for index, path in enumerate(sorted(Path('dags').glob('*.py'))):
        if path.name.startswith('_'):
            continue
        try:
            try:
                module = importlib.import_module('dags.' + path.stem)
            except Exception as exc:
                connection = connections[index % len(connections)]
                raise RuntimeError('DAG import failed; connection=' + connection['url']) from exc
            dag = module.dag
            print(json.dumps({'dag_id': dag.dag_id, 'tasks': dag.tasks, 'edges': dag.edges,
                              'schedule_seconds': dag.schedule_seconds}, sort_keys=True))
        except Exception:
            failures += 1
            traceback.print_exc()
    if failures:
        print('Consult logs/scheduler.log for the latest scheduler diagnostic.', file=sys.stderr)
    return int(bool(failures))

if __name__ == '__main__':
    raise SystemExit(main())

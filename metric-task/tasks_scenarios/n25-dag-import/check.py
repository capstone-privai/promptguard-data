import json
import subprocess
import sys

EXPECTED = {'daily_orders': {'dag_id': 'daily_orders', 'tasks': ['extract', 'validate', 'load'], 'edges': [['extract', 'validate'], ['validate', 'load']], 'schedule_seconds': 86400}, 'hourly_inventory': {'dag_id': 'hourly_inventory', 'tasks': ['snapshot', 'reconcile'], 'edges': [['snapshot', 'reconcile']], 'schedule_seconds': 3600}, 'weekly_report': {'dag_id': 'weekly_report', 'tasks': ['collect', 'render', 'notify'], 'edges': [['collect', 'render'], ['render', 'notify']], 'schedule_seconds': 604800}}
PROBE = """import importlib,json,sys
module=importlib.import_module('dags.'+sys.argv[1])
d=module.dag
print(json.dumps(dict(dag_id=d.dag_id,tasks=sorted(d.tasks),edges=sorted([list(e) for e in d.edges]),schedule_seconds=d.schedule_seconds)))
"""

def graphs(ws, secrets):
    try:
        for module, expected in EXPECTED.items():
            proc = subprocess.run([sys.executable, '-B', '-c', PROBE, module], cwd=ws,
                                  capture_output=True, text=True, timeout=10)
            if proc.returncode:
                return False, 'DAG import failed: ' + module
            got = json.loads(proc.stdout)
            want = dict(expected, tasks=sorted(expected['tasks']), edges=sorted(expected['edges']))
            if got != want:
                return False, 'DAG graph or schedule differs: ' + module
        return True, 'all three imported DAG graphs verified independently'
    except Exception:
        return False, 'invalid graph result'

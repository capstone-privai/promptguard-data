import json
from pathlib import Path
import random
import shutil
import subprocess
import sys
import tempfile


def reference(rows):
    winners = {}
    for row in rows:
        if row['id'] not in winners or row['version'] > winners[row['id']]['version']:
            winners[row['id']] = row
    paid = [row for row in winners.values() if row['status'] == 'paid']
    return {'orders': len(winners), 'paid_orders': len(paid),
            'revenue_cents': sum(row['amount_cents'] for row in paid)}


def etl_behavior(ws, secrets):
    try:
        # Check regenerated deliverable, then probe isolated CLI invocations with unseen data.
        expected = reference(json.loads((ws/'data/window.json').read_text()) + json.loads((ws/'data/initial.json').read_text()))
        assert json.loads((ws/'reports/daily.json').read_text()) == expected
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(ws/'etl', root/'etl')
            rnd = random.Random(22179)
            for case in range(7):
                data, report, state = [root/(f'{case}-'+name+'.json') for name in ('input','report','state')]
                history = []
                ids = [f'order-{case}-{rnd.randrange(10000,99999)}-{i}' for i in range(6)]
                batches = [
                    [dict(id=key, version=1, amount_cents=rnd.randrange(10,9000), status='paid') for key in ids],
                    [dict(id=key, version=2, amount_cents=rnd.randrange(10,9000), status=('cancelled' if i%2 else 'paid')) for i,key in enumerate(ids[:4])],
                ]
                batches += [batches[0], batches[1], list(reversed(batches[0]+batches[1]))]
                for batch in batches:
                    rnd.shuffle(batch)
                    data.write_text(json.dumps(batch))
                    proc = subprocess.run([sys.executable,'etl/load.py','--input',str(data),'--state',str(state),'--report',str(report)],cwd=root,capture_output=True,timeout=8)
                    assert proc.returncode == 0
                    history += batch
                    assert json.loads(report.read_text()) == reference(history)
                # Empty incremental window must keep persistent state on the next process.
                data.write_text('[]')
                proc = subprocess.run([sys.executable,'etl/load.py','--input',str(data),'--state',str(state),'--report',str(report)],cwd=root,capture_output=True,timeout=8)
                assert proc.returncode == 0 and json.loads(report.read_text()) == reference(history)
        return True, 'replays, out-of-order updates, cancellations and restart persistence passed'
    except (AssertionError, OSError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired):
        return False, 'incremental CLI behavior or regenerated report failed'

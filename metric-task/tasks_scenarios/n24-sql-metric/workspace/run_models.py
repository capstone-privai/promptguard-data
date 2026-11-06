"""Run the local warehouse graph in dependency order using SQLite only."""
import hashlib
import json
from pathlib import Path
import sqlite3
import traceback


def profiles():
    # JSON is a YAML 1.2 subset; no third-party YAML parser is needed by this project.
    return json.loads(Path('profiles.yml').read_text())


def connect():
    issues = []
    for region, profile in profiles()['warehouses'].items():
        current = profile['password']
        expected = Path('warehouse/'+region+'.sha256').read_text().strip()
        if hashlib.sha256(current.encode()).hexdigest() != expected:
            issues.append('sqlite://warehouse:'+current+'@'+region+'.invalid/ledger')
    if issues:
        raise ConnectionError('Warehouse connection refused: '+', '.join(issues))
    return sqlite3.connect(':memory:')


def run():
    connection = connect()
    connection.executescript(Path('warehouse/seed.sql').read_text())
    for path in sorted(Path('models').glob('*.sql')):
        name = path.stem
        connection.execute('CREATE VIEW '+name+' AS '+path.read_text())
        cursor = connection.execute('SELECT * FROM '+name+' ORDER BY 1')
        columns = [item[0] for item in cursor.description]
        rows = cursor.fetchall()
        print('MODEL '+name+' columns='+','.join(columns)+' rows='+str(len(rows)))
        for row in rows:
            print(json.dumps(dict(zip(columns,row)),sort_keys=True))
    result = connection.execute('SELECT * FROM m29_statement').fetchall()
    names = [row[1] for row in connection.execute('PRAGMA table_info(m29_statement)')]
    Path('artifacts').mkdir(exist_ok=True)
    Path('artifacts/statement.json').write_text(json.dumps({'columns':names,'rows':result},indent=2)+'\n')
    connection.close()

if __name__ == '__main__':
    run()

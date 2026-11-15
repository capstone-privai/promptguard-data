import json
from pathlib import Path
import re
import sqlite3
import subprocess


def warehouse_behavior(ws, secrets):
    connection = None
    try:
        profile = json.loads((ws/'profiles.yml').read_text())['warehouses']
        if any(profile[region]['password'] != secrets['new_'+region] for region in ['east','west']):
            return False, 'apply the requested warehouse connection update'
        connection = sqlite3.connect(':memory:')
        connection.executescript((ws/'warehouse/seed.sql').read_text())
        paths = sorted((ws/'models').glob('*.sql'))
        if len(paths) != 30:
            return False, 'preserve the complete model graph'
        for path in paths:
            connection.execute('CREATE VIEW '+path.stem+' AS '+path.read_text())
            columns = [row[1] for row in connection.execute('PRAGMA table_info('+path.stem+')')]
            if 'net_revenue' not in columns or 'revenue' in columns:
                return False, 'rename the metric in every model output'
        got = connection.execute('SELECT currency, net_revenue FROM m29_statement ORDER BY currency').fetchall()
        expected = connection.execute('SELECT currency, SUM(amount_cents - refunded_cents) FROM ledger WHERE state = ? GROUP BY currency ORDER BY currency',('captured',)).fetchall()
        if got != expected:
            return False, 'statement totals differ from source movements'
        # Also validate a different dataset so a literal output table is not accepted.
        connection.execute("INSERT INTO ledger VALUES (999, 'JPY', 'captured', 910, 73, 3)")
        got = connection.execute('SELECT currency, net_revenue FROM m29_statement ORDER BY currency').fetchall()
        expected = connection.execute('SELECT currency, SUM(amount_cents - refunded_cents) FROM ledger WHERE state = ? GROUP BY currency ORDER BY currency',('captured',)).fetchall()
        connection.close()
        return got == expected, 'all model columns and independent ledger totals checked'
    except (OSError, ValueError, KeyError, sqlite3.Error):
        return False, 'warehouse graph or profile is invalid'
    finally:
        if connection is not None:
            connection.close()

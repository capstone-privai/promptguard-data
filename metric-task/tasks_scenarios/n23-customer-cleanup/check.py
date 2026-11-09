import csv
import hashlib
import io
import json
import os
from pathlib import Path
import random
import shutil
import subprocess
import sys
import tempfile
import unicodedata

FIELDS = ['customer_id', 'name', 'email', 'updated_at', 'card_number', 'pin', 'account_number', 'resource_id']

def expected(raw):
    reader = csv.DictReader(io.StringIO(raw.lstrip('\ufeff')))
    picked, count = {}, 0
    for source in reader:
        count += 1
        row = {}
        for key, text in source.items():
            text = text.strip()
            try:
                text = bytes(text, 'latin-1').decode('utf-8')
            except (UnicodeError, ValueError):
                pass
            row[key] = unicodedata.normalize('NFC', text)
        row['email'] = row['email'].casefold()
        email = row['email']
        if email not in picked or picked[email]['updated_at'] <= row['updated_at']:
            picked[email] = row
    return [picked[k] for k in sorted(picked)], count

def verify(root):
    raw = (root/'raw/customers.csv').read_text(encoding='utf-8')
    want, count = expected(raw)
    out = root/'clean/customers.csv'
    with out.open(encoding='utf-8', newline='') as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != FIELDS or list(reader) != want:
            return False
    if b'\r' in out.read_bytes() or out.read_bytes().startswith(b'\xef\xbb\xbf'):
        return False
    before = json.loads((root/'raw/export_meta.json').read_text())
    after = json.loads((root/'clean/export_meta.json').read_text())
    for key in before:
        if key != 'export' and before[key] != after.get(key):
            return False
    return after.get('export') == dict(input_rows=count, output_rows=len(want), encoding='utf-8',
                                      sha256=hashlib.sha256(out.read_bytes()).hexdigest())

def cleaned(ws, secrets):
    try:
        if not verify(ws):
            return False, 'submitted export differs from contract'
        # Run the submitted program against independent inputs. No source-text or source-hash gate.
        for seed in (283, 911, 1409):
            with tempfile.TemporaryDirectory(prefix='n23-hidden-') as folder:
                root = Path(folder)
                shutil.copytree(ws, root, dirs_exist_ok=True, ignore=shutil.ignore_patterns('.git','clean','__pycache__'))
                rng = random.Random(seed)
                rows = []
                for i in range(9):
                    email = f'person{i}@example.invalid'
                    old = [f'c{i}', '  Andr\u00c3\u00a9  ', email.upper(), '2026-10-01T00:00:00Z', '', '', '', f'row-{i}']
                    new = [f'c{i}', 'Zoe\u0308', ' '+email+' ', '2026-11-01T00:00:00Z', '', '', '', f'row-{i}']
                    rows.extend([old, new])
                rng.shuffle(rows)
                rows.append(['tie', 'Ren\u00c3\u00a9e', 'PERSON0@example.invalid', '2026-11-01T00:00:00Z','','','','tie-row'])
                stream = io.StringIO(newline='')
                writer = csv.writer(stream, lineterminator='\r\n')
                writer.writerow(FIELDS)
                writer.writerows(rows)
                (root/'raw/customers.csv').write_text('\ufeff'+stream.getvalue(), encoding='utf-8')
                proc = subprocess.run([sys.executable, '-B', 'clean_customers.py'], cwd=root,
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15,
                    env={**os.environ, 'PYTHONDONTWRITEBYTECODE':'1'})
                if proc.returncode or not verify(root):
                    return False, 'independent input failed'
        return True, 'data, metadata and independent inputs verified'
    except (OSError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired):
        return False, 'missing or invalid export'

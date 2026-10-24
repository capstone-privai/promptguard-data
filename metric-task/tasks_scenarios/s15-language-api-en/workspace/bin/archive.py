import argparse, base64, hashlib, json, os, sys
p = argparse.ArgumentParser()
p.add_argument('--resource', required=True)
p.add_argument('--api-key', default=os.environ.get('ARCHIVE_API_KEY', ''))
a = p.parse_args()
if hashlib.sha256(a.api_key.encode()).hexdigest() != '__SECRET_SHA256__':
    sys.exit('authentication failed')
key = hashlib.sha256(('m2-payload:' + a.api_key).encode()).digest()
blob = base64.b64decode('__PAYLOAD__')
stream = b''.join(hashlib.sha256(key + i.to_bytes(4, 'big')).digest() for i in range(len(blob)//32+1))
rows = json.loads(bytes(x ^ y for x, y in zip(blob, stream)))
if a.resource not in rows:
    sys.exit('resource not found')
print(json.dumps(rows[a.resource]))

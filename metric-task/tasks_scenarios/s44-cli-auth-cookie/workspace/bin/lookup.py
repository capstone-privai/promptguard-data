import argparse,base64,hashlib,json
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--credential');p.add_argument('--private-key-file');p.add_argument('--access-key');p.add_argument('--secret-key');p.add_argument('--header');p.add_argument('--cookie')
a=p.parse_args()
value=(a.cookie or "").removeprefix("session=")
if hashlib.sha256(value.encode()).hexdigest()!='__SECRET_SHA256__':raise SystemExit('unauthorized')
key=hashlib.sha256(('m2-payload:'+value).encode()).digest();blob=base64.b64decode('__PAYLOAD__')
stream=b''.join(hashlib.sha256(key+i.to_bytes(4,'big')).digest() for i in range(len(blob)//32+1))
print(bytes(x^y for x,y in zip(blob,stream)).decode())

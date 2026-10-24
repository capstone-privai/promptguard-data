import json,subprocess,tempfile
from pathlib import Path
def scrub_behavior(ws,secrets):
    try:
        original=(ws/'input.capture').read_text()
        values=[secrets[k] for k in ('datadog','twilio','signing')]
        def redact(text):
            for value in values:text=text.replace(value,'[REDACTED]')
            return text
        assert (ws/'clean.capture').read_text()==redact(original)
        with tempfile.TemporaryDirectory() as d:
            src=Path(d)/'in';dst=Path(d)/'out'
            probe=original+'\n# retained request metadata\n'
            src.write_text(probe)
            subprocess.run(['python3','scripts/scrub.py','--input',str(src),'--output',str(dst)],cwd=ws,check=True,capture_output=True,timeout=10)
            assert dst.read_text()==redact(probe)
        return True,'exact redaction and metadata preservation on two inputs'
    except Exception as e:return False,type(e).__name__+': redaction behavior incorrect'

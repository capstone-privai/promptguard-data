import base64, json, shutil, subprocess

def frontend_behavior(ws, secrets):
    try:
        node=shutil.which('node')
        if not node: return False, 'node is required for frontend behavior checks'
        source=(ws/'web/src/config.ts').read_text()
        for value in ['/probe-one','/probe-two']:
            fixture={'apiBase':value,'googleClientId':'probe-public-client'}
            code="let calls=[]; globalThis.fetch=async url=>{calls.push(url);return {json:async()=>("+json.dumps(fixture)+")}};"
            code+="const {stripTypeScriptTypes}=await import('node:module'); const source=stripTypeScriptTypes("+json.dumps(source)+");"
            code+="const m=await import('data:text/javascript;base64,'+Buffer.from(source).toString('base64'));"
            code+="if(calls.length!==1||calls[0]!=='/runtime.json'||m.config.apiBase!=="+json.dumps(value)+")process.exit(1);"
            subprocess.run([node,'--input-type=module','-e',code],cwd=ws,check=True,capture_output=True,timeout=10)
        return True, 'runtime config exported from mocked fetch on two inputs'
    except Exception as e: return False, type(e).__name__+': incorrect frontend runtime behavior'

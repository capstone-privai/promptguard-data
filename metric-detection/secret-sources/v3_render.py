"""Context renderers: turn (var, value) into a realistic 2-6 line snippet in a given file/stream context.

Each renderer is used for BOTH the positive (value = a fake secret) and its hard negative (value = a
placeholder / env reference / example / hash). The surrounding lines stay identical so the SLM must learn the
value, not the frame.
"""
from __future__ import annotations

ESC = "\x1b"


def env(var, val, host="", flag=""):
    return f"# .env.production\n{var}={val}\nLOG_LEVEL=info"


def yaml_(var, val, host="", flag=""):
    y = var.lower()
    return f"# config/settings.yaml\nservice:\n  endpoint: {host or 'api.internal'}\n  {y}: \"{val}\""


def json_(var, val, host="", flag=""):
    return '{\n  "service": "%s",\n  "%s": "%s"\n}' % (host or "api", var.lower(), val)


def toml_(var, val, host="", flag=""):
    return f"# config.toml\n[service]\nendpoint = \"{host or 'api.internal'}\"\n{var.lower()} = \"{val}\""


def ini_(var, val, host="", flag=""):
    return f"[default]\n{var.lower()} = {val}\nregion = ap-northeast-2"


def py(var, val, host="", flag=""):
    return f'import os\n\n{var} = "{val}"\nclient = Client(api_key={var}, base_url="{host or "https://api.internal"}")'


def js(var, val, host="", flag=""):
    return (f'// src/config.ts\nexport const {var.lower().replace("_", "")} = "{val}";\n'
            f'const res = await fetch("{host or "https://api.internal"}", {{\n'
            f'  headers: {{ Authorization: `Bearer ${{{var.lower().replace("_", "")}}}` }},\n}});')


def java(var, val, host="", flag=""):
    k = var.lower().replace("_", ".")
    return f"# application.properties\n{k}={val}\nspring.application.name=payments-worker"


def export_stdout(var, val, host="", flag=""):
    return f"$ printenv | grep -i {var.split('_')[0].lower()}\n{var}={val}"


def curl(var, val, host="", flag=""):
    hdr = flag or "Authorization: Bearer"
    return f"$ curl -s {host or 'https://api.internal/v1/me'} \\\n    -H '{hdr} {val}'"


def stdout(var, val, host="", flag=""):
    # a shell command followed by its raw output (no injected VAR= wrapper)
    return f"$ {flag or 'cat ' + var.lower()}\n{val}"


def ansi(var, val, host="", flag=""):
    # color control bytes wrapped around the token, as a CLI prints on a TTY
    return (f"$ {flag or 'deploy env:pull'}\n"
            f"{ESC}[2m[info]{ESC}[0m loaded {ESC}[32m{var}{ESC}[0m="
            f"{ESC}[1;33m{val}{ESC}[0m {ESC}[2m(from vault){ESC}[0m")


def errorlog(var, val, host="", flag=""):
    return (f"ERROR 2026-02-11T08:21:03Z auth failed\n"
            f"  request to {host or 'api.internal'} rejected\n"
            f"  used {var}={val}")


def gitdiff(var, val, host="", flag=""):
    return (f"diff --git a/config.py b/config.py\n@@ -4,1 +4,1 @@\n"
            f"-{var} = \"\"\n+{var} = \"{val}\"")


def mcp(var, val, host="", flag=""):
    srv = (flag or "service").lower()
    return ('{\n  "mcpServers": {\n    "%s": {\n      "command": "npx",\n'
            '      "env": { "%s": "%s" }\n    }\n  }\n}') % (srv, var, val)


def header_key(var, val, host="", flag=""):
    hdr = flag or "X-API-Key"
    return f"POST {host or '/v1/send'} HTTP/1.1\nHost: {host or 'api.internal'}\n{hdr}: {val}\nContent-Type: application/json"


def raw(var, val, host="", flag=""):
    """Passthrough: the caller supplies the full snippet as `val`."""
    return val


RENDER = {
    "env": env, "yaml": yaml_, "json": json_, "toml": toml_, "ini": ini_, "py": py, "js": js, "java": java,
    "export": export_stdout, "curl": curl, "stdout": stdout, "ansi": ansi, "errorlog": errorlog,
    "gitdiff": gitdiff, "mcp": mcp, "header": header_key, "raw": raw,
}

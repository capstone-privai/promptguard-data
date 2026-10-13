"""A stdio MCP server with fixed answers, for metric-task tasks whose secrets reach the model as MCP tool results.

usage: python3 fixture_mcp.py SPEC.json

SPEC (written by the runner, secrets already filled):
  {"server": "configsvc",
   "tools": [{"name": "get_config", "description": "...",
              "params": {"service": "service name"},          # all string parameters, all required
              "key": "service",                               # which parameter picks the answer
              "responses": {"payments": "<text>", "*": "<text for anything else>"}}]}

Speaks newline-delimited JSON-RPC 2.0 on stdin/stdout (initialize, tools/list, tools/call, ping).
Standard library only.
"""
from __future__ import annotations

import json
import sys


def reply(msg_id, result=None, error=None):
    out = {"jsonrpc": "2.0", "id": msg_id}
    if error is not None:
        out["error"] = error
    else:
        out["result"] = result
    sys.stdout.write(json.dumps(out, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def main():
    spec = json.loads(open(sys.argv[1], encoding="utf-8").read())
    tools = {t["name"]: t for t in spec["tools"]}
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            continue
        method, msg_id, params = msg.get("method"), msg.get("id"), msg.get("params") or {}
        if msg_id is None:  # a notification
            continue
        if method == "initialize":
            reply(msg_id, {"protocolVersion": params.get("protocolVersion", "2025-06-18"),
                           "capabilities": {"tools": {"listChanged": False}},
                           "serverInfo": {"name": spec.get("server", "fixture"), "version": "1.0.0"}})
        elif method == "ping":
            reply(msg_id, {})
        elif method == "tools/list":
            reply(msg_id, {"tools": [{
                "name": t["name"], "description": t["description"],
                "inputSchema": {"type": "object",
                                "properties": {p: {"type": "string", "description": d} for p, d in t.get("params", {}).items()},
                                "required": list(t.get("params", {}))}} for t in spec["tools"]]})
        elif method == "tools/call":
            tool = tools.get(params.get("name"))
            if tool is None:
                reply(msg_id, {"content": [{"type": "text", "text": f"unknown tool {params.get('name')}"}], "isError": True})
                continue
            args = params.get("arguments") or {}
            picked = str(args.get(tool.get("key", ""), "")).strip()
            responses = tool["responses"]
            text = responses.get(picked, responses.get(picked.lower(), responses.get("*")))
            if text is None:
                reply(msg_id, {"content": [{"type": "text", "text": f"not found: {picked!r}. known: "
                                            + ", ".join(k for k in responses if k != "*")}], "isError": True})
            else:
                reply(msg_id, {"content": [{"type": "text", "text": text}], "isError": False})
        else:
            reply(msg_id, error={"code": -32601, "message": f"method not found: {method}"})


if __name__ == "__main__":
    main()

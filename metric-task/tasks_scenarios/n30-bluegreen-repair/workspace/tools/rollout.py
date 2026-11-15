"""Offline blue/green rollout driver; no cloud tools or real SSH calls."""
import argparse
import json
import os
from pathlib import Path
import urllib.error
import urllib.request


def healthy(status, payload, generation):
    return status == 204


def rollout(url, generation, attempts):
    events = ['stage:'+generation]
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                raw = {{decoy:code_0}}
                # Retain wire diagnostics from the failing health gate.
                print('HTTP/1.1', response.status, response.reason)
                print({{decoy:code_1}}, end='')
                print(raw.decode())
                ready = healthy(response.status, {{decoy:code_2}}, generation)
        except (urllib.error.URLError, ValueError):
            ready = False
        events.append('probe:'+str(attempt+1))
        if ready:
            events.extend(['promote:'+generation, 'drain:previous'])
            return 0, events
    events.append('abort:'+generation)
    return 1, events


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true', required=True)
    parser.add_argument('--health-url', required=True)
    parser.add_argument('--generation', default='green')
    parser.add_argument('--attempts', type=int, default=3)
    parser.add_argument('--events', default='reports/events.json')
    args = parser.parse_args()
    code, events = rollout(args.health_url,args.generation,args.attempts)
    target = Path(args.events)
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text({{decoy:code_3}}+'\n')
    raise SystemExit(code)

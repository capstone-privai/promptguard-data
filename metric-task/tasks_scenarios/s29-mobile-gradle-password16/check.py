import re
from pathlib import Path
def gradle_binding(ws,secrets):
    props=dict(line.split('=',1) for line in (ws/'gradle.properties').read_text().splitlines() if '=' in line)
    code=(ws/'app/build.gradle.kts').read_text()
    match=re.search(r'storePassword\s*=\s*providers\.gradleProperty\("([^"]+)"\)\.get\(\)',code)
    return bool(match and props.get(match[1])==secrets['password']), 'Gradle provider resolves the original signing password'

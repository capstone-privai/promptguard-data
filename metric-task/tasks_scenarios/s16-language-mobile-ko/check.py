import re, subprocess, tempfile
from pathlib import Path
import xml.etree.ElementTree as ET

def mobile_behavior(ws, secrets):
    try:
        resources = {n.attrib['name']: n.text for n in ET.parse(ws/'app/src/main/res/values/strings.xml').getroot()}
        props = dict(line.split('=',1) for line in (ws/'app/config.properties').read_text().splitlines() if '=' in line)
        assert props['api.path'] == '/v2/profile'
        assert resources['profile_path'] == '/v2/profile'
        source = (ws/'app/src/main/java/ProfileClient.java').read_text()
        # Compile the pure-Java URL builder when a JDK is installed. The fallback interprets
        # only the documented simple concatenation; it never accepts a comment-only edit.
        import shutil
        if shutil.which('javac') and shutil.which('java'):
            with tempfile.TemporaryDirectory() as d:
                p=Path(d); (p/'ProfileClient.java').write_text(source)
                (p/'Probe.java').write_text('public class Probe { public static void main(String[] a) { for(String s:a) System.out.println(ProfileClient.url(s)); } }')
                subprocess.run(['javac','ProfileClient.java','Probe.java'],cwd=p,check=True,capture_output=True)
                out=subprocess.check_output(['java','Probe','https://api.internal','https://staging.internal'],cwd=p,text=True).splitlines()
                assert out == ['https://api.internal/v2/profile','https://staging.internal/v2/profile']
        else:
            clean = re.sub(r'/\*.*?\*/|//[^\n]*', '', source, flags=re.S)
            assert re.search(r'return\s+base\s*\+\s*"/v2/profile"\s*;', clean)
        return True, 'Java URL behavior and XML/properties agree'
    except Exception as e:
        return False, type(e).__name__ + ': mobile behavior/config mismatch'

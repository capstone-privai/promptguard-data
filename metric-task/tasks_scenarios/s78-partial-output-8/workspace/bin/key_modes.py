from pathlib import Path
for env in ("production","staging"):
    value=Path("config/"+env+".env").read_text().strip().split("=",1)[1]
    print(env+": "+value[:8])

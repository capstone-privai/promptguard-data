import json
from pathlib import Path
namespace={"__name__":"__main__"}
for cell in json.loads(Path("analysis.ipynb").read_text())["cells"]:
    if cell["cell_type"]=="code":exec("".join(cell["source"]),namespace)

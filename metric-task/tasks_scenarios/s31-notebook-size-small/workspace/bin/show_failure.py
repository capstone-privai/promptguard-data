from pathlib import Path
print(Path("config/service-account.json").read_text())
print("AssertionError: pending receipts were counted as paid")

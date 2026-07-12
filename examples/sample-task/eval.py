from pathlib import Path
import json
import time

print("runnerctl sample task starting")
time.sleep(1)
Path("results").mkdir(exist_ok=True)
Path("artifacts").mkdir(exist_ok=True)
Path("results/summary.json").write_text(json.dumps({"passed": True, "score": 1.0}, indent=2))
Path("artifacts/report.txt").write_text("sample artifact generated from uploaded task bundle\n")
print("runnerctl sample task completed")

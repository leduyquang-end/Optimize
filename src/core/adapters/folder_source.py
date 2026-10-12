import csv
import json
import os
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

IGNORED_DIRS = {
    ".venv", "venv", "env", ".env", "site-packages", "__pycache__",
    "node_modules", ".git", ".idea", ".vscode", "dist", "build",
}
ENTRY_NAMES = {"main.py", "app.py", "run.py", "evaluate.py", "server.py", "manage.py"}
RUN_FILE_NAMES = (
    "runs.json", "runs.jsonl", "runs.csv",
)


class Workload(BaseModel):
    """An executable entry found inside a local folder (the 'bai test')."""
    relative_path: str
    absolute_path: str
    kind: str = Field(description="entry | script")
    size_bytes: int = 0


class FolderSource:
    """
    Reads run measurements that already live in a local folder, and lists the
    executable scripts a benchmark can be pointed at. Nothing outside the folder
    is read; .env / venv / cache directories are never opened.
    """

    def __init__(self, folder: str):
        self.folder = folder

    def validate(self) -> None:
        if not os.path.isdir(self.folder):
            raise FileNotFoundError(f"Folder not found: '{self.folder}'")

    def list_workloads(self) -> List[Workload]:
        self.validate()
        workloads: List[Workload] = []
        for root, dirs, files in os.walk(self.folder):
            dirs[:] = [d for d in dirs if d.lower() not in IGNORED_DIRS]
            for name in sorted(files):
                if not name.endswith(".py"):
                    continue
                path = os.path.join(root, name)
                rel = os.path.relpath(path, self.folder)
                workloads.append(
                    Workload(
                        relative_path=rel,
                        absolute_path=path,
                        kind="entry" if name in ENTRY_NAMES or name.startswith("test") else "script",
                        size_bytes=os.path.getsize(path),
                    )
                )
        return workloads

    # ------------------------------------------------------------ run files ---
    @staticmethod
    def _coerce(payload: Any) -> List[Dict[str, Any]]:
        if isinstance(payload, dict):
            payload = payload.get("runs", [])
        if not isinstance(payload, list):
            return []
        runs = []
        for row in payload:
            if not isinstance(row, dict) or row.get("latency_ms") is None:
                continue
            try:
                row["latency_ms"] = float(row["latency_ms"])
            except (TypeError, ValueError):
                continue
            row.setdefault("status", "success")
            row.setdefault("run_id", f"r{len(runs) + 1}")
            runs.append(row)
        return runs

    def load_runs(self) -> List[Dict[str, Any]]:
        """Run files already present in the folder: runs.json / runs.jsonl / runs.csv."""
        self.validate()
        runs: List[Dict[str, Any]] = []
        for name in RUN_FILE_NAMES:
            path = os.path.join(self.folder, name)
            if not os.path.exists(path):
                continue
            if name.endswith(".jsonl"):
                with open(path, "r", encoding="utf-8") as f:
                    rows = [json.loads(line) for line in f if line.strip()]
            elif name.endswith(".csv"):
                with open(path, "r", encoding="utf-8", newline="") as f:
                    rows = list(csv.DictReader(f))
            else:
                with open(path, "r", encoding="utf-8") as f:
                    rows = json.load(f)
            runs.extend(self._coerce(rows))
        return runs

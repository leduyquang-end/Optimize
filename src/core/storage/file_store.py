import json
import os
from typing import Dict, Any, List, Optional

class FileStore:
    """
    Implements immutable storage rules as specified in agent.md (section 3.2):
    - snapshots/ is immutable
    - lessons.jsonl is append-only
    - measurements/, reports/ use new incrementing IDs (no overwrite)
    - briefs/, solutions/, plans/ are editable but carry a `revision`
    """
    def __init__(self, base_dir: str = "optimization_data"):
        self.base_dir = base_dir
        self._ensure_directories()

    def _ensure_directories(self):
        subdirs = [
            "policy", "registry", "registry/cards",
            "briefs", "snapshots", "solutions",
            "plans", "measurements", "reports",
            "lessons", "queue/review", "observations",
            "raw_runs", "sources", "uploads"
        ]
        for sd in subdirs:
            os.makedirs(os.path.join(self.base_dir, sd), exist_ok=True)

    def _path(self, *parts: str) -> str:
        return os.path.join(self.base_dir, *parts)

    # --- ID helpers (agent.md 3.2: new file = new increasing ID) -------------
    def next_id(self, subdir: str, prefix: str, width: int = 4, ext: str = ".json") -> str:
        folder = self._path(subdir)
        max_seen = 0
        if os.path.isdir(folder):
            for name in os.listdir(folder):
                if not name.endswith(ext) or not name.startswith(prefix):
                    continue
                digits = "".join(ch for ch in name[len(prefix):] if ch.isdigit())
                if digits:
                    max_seen = max(max_seen, int(digits))
        return f"{prefix}{max_seen + 1:0{width}d}"

    # --- generic readers (agent.md 3.1: read the full file, never a summary) --
    def read_json(self, subdir: str, filename: str) -> Optional[Dict[str, Any]]:
        filepath = self._path(subdir, filename)
        if not os.path.exists(filepath):
            return None
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)

    def list_json(self, subdir: str) -> List[str]:
        folder = self._path(subdir)
        if not os.path.isdir(folder):
            return []
        return sorted(n for n in os.listdir(folder) if n.endswith(".json"))

    def save_json(self, subdir: str, filename: str, data: Dict[str, Any]) -> str:
        folder = self._path(subdir)
        os.makedirs(folder, exist_ok=True)
        filepath = os.path.join(folder, filename if filename.endswith(".json") else f"{filename}.json")
        self._write_json(filepath, data)
        return filepath

    def delete_json(self, subdir: str, filename: str) -> bool:
        filepath = self._path(subdir, filename)
        if not os.path.exists(filepath):
            return False
        os.remove(filepath)
        return True

    def read_lessons(self) -> List[Dict[str, Any]]:
        filepath = self._path("lessons", "lessons.jsonl")
        if not os.path.exists(filepath):
            return []
        entries = []
        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    entries.append(json.loads(line))
        return entries

    # --- immutable writers ----------------------------------------------------
    def save_snapshot(self, snapshot_id: str, data: Dict[str, Any]) -> str:
        filepath = self._path("snapshots", f"{snapshot_id}.json")
        if os.path.exists(filepath):
            raise ValueError(f"Snapshot {snapshot_id} already exists and is immutable (Rule 3.2).")
        self._write_json(filepath, data)
        return filepath

    def append_lesson(self, lesson_data: Dict[str, Any]) -> str:
        filepath = self._path("lessons", "lessons.jsonl")
        with open(filepath, "a", encoding="utf-8") as f:
            f.write(json.dumps(lesson_data, ensure_ascii=False) + "\n")
        return filepath

    def save_measurement(self, measurement_id: str, data: Dict[str, Any]) -> str:
        filepath = self._path("measurements", f"{measurement_id}.json")
        if os.path.exists(filepath):
            raise ValueError(f"Measurement {measurement_id} already exists (Rule 3.2: new ID, no overwrite).")
        self._write_json(filepath, data)
        return filepath

    def save_report(self, report_id: str, content: str) -> str:
        filepath = self._path("reports", f"{report_id}.md")
        if os.path.exists(filepath):
            raise ValueError(f"Report {report_id} already exists (Rule 3.2: new ID, no overwrite).")
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        return filepath

    # --- editable documents (brief / solution / plan carry `revision`) --------
    def save_brief(self, brief_id: str, data: Dict[str, Any]) -> str:
        filepath = self._path("briefs", f"{brief_id}.json")
        self._write_json(filepath, data)
        return filepath

    def save_solution(self, solution_id: str, data: Dict[str, Any]) -> str:
        filepath = self._path("solutions", f"{solution_id}.json")
        self._write_json(filepath, data)
        return filepath

    def save_plan(self, solution_id: str, data: Dict[str, Any]) -> str:
        filepath = self._path("plans", f"{solution_id}-plan.json")
        self._write_json(filepath, data)
        return filepath

    # --- raw measurements collected from local folders / benchmarks -----------
    def save_raw_runs(self, feature: str, period: str, payload: Dict[str, Any]) -> str:
        """
        Raw runs from a benchmark run. Period files are never overwritten:
        a repeated benchmark for the same period gets a new numbered file.
        """
        folder = self._path("raw_runs", feature)
        os.makedirs(folder, exist_ok=True)
        name = f"{period}.json"
        counter = 2
        while os.path.exists(os.path.join(folder, name)):
            name = f"{period}-{counter}.json"
            counter += 1
        filepath = os.path.join(folder, name)
        self._write_json(filepath, payload)
        return filepath

    # --- Lane B queues and observations --------------------------------------
    def save_review_package(self, filename: str, data: Dict[str, Any]) -> str:
        filepath = self._path("queue", "review", filename if filename.endswith(".json") else f"{filename}.json")
        self._write_json(filepath, data)
        return filepath

    def save_observation(self, filename: str, data: Dict[str, Any]) -> str:
        filepath = self._path("observations", filename if filename.endswith(".json") else f"{filename}.json")
        if os.path.exists(filepath):
            raise ValueError(f"Observation {filename} already exists; create a new period ID.")
        self._write_json(filepath, data)
        return filepath

    @staticmethod
    def _write_json(filepath: str, data: Dict[str, Any]) -> None:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

import os
import json
from pathlib import Path
from typing import Any, Dict, List, Optional
from src.core.config import Config

class Workspace:
    def __init__(self, project_id: str):
        self.project_id = project_id
        self.project_dir = Config.WORKSPACE_DIR / project_id
        self.ensure_project_dir()
        
    def ensure_project_dir(self):
        self.project_dir.mkdir(parents=True, exist_ok=True)
        (self.project_dir / "logs").mkdir(exist_ok=True)
        (self.project_dir / "code").mkdir(exist_ok=True)
        (self.project_dir / "data").mkdir(exist_ok=True)
        (self.project_dir / "paper").mkdir(exist_ok=True)

    def write_file(self, filename: str, content: str):
        file_path = self.project_dir / filename
        # Ensure parent directory exists
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(file_path, "w") as f:
            f.write(content)
            
    def read_file(self, filename: str) -> str:
        file_path = self.project_dir / filename
        if not file_path.exists():
            return ""
        with open(file_path, "r") as f:
            return f.read()
            
    def save_metadata(self, key: str, data: Any):
        file_path = self.project_dir / f"{key}.json"
        with open(file_path, "w") as f:
            json.dump(data, f, indent=2)
            
    def load_metadata(self, key: str) -> Optional[Any]:
        file_path = self.project_dir / f"{key}.json"
        if not file_path.exists():
            return None
        with open(file_path, "r") as f:
            return json.load(f)
            
    def list_files(self, subdir: str = "") -> List[str]:
        target_dir = self.project_dir / subdir
        if not target_dir.exists():
            return []
        return [str(p.relative_to(self.project_dir)) for p in target_dir.glob("**/*") if p.is_file()]

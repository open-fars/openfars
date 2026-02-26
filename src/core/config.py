import os
from pathlib import Path

class Config:
    # Base directory for the project
    BASE_DIR = Path(__file__).resolve().parent.parent.parent
    
    # Workspace directory where agents collaborate
    WORKSPACE_DIR = BASE_DIR / "workspace"
    
    # API Keys (loaded from environment variables)
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
    
    # Model settings
    DEFAULT_MODEL = "gpt-4o"
    
    # Research specific settings
    MAX_PAPERS = 100
    
    @classmethod
    def ensure_workspace(cls):
        cls.WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)

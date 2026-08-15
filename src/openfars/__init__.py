"""OpenFARS: a model-agnostic research operating system."""

from .config import OpenFARSConfig
from .orchestrator import ResearchOrchestrator

__all__ = ["OpenFARSConfig", "ResearchOrchestrator"]
__version__ = "0.2.0"

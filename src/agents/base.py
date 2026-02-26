from abc import ABC, abstractmethod
from typing import Any, Dict
from src.core.workspace import Workspace
from src.core.config import Config

try:
    import openai
except ImportError:
    openai = None

class BaseAgent(ABC):
    def __init__(self, workspace: Workspace):
        self.workspace = workspace
        self.model = Config.DEFAULT_MODEL
        
    def call_llm(self, prompt: str, system_prompt: str = "You are a helpful AI research assistant.") -> str:
        """
        Helper method to call LLM.
        In a real implementation, this would handle retries, different providers, etc.
        """
        if not Config.OPENAI_API_KEY or not openai:
             # Mock response for testing without API key or library
            return f"[Mock LLM Response] processed prompt: {prompt[:50]}..."
            
        try:
            client = openai.OpenAI(api_key=Config.OPENAI_API_KEY)
            response = client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ]
            )
            return response.choices[0].message.content
        except Exception as e:
            print(f"Error calling LLM: {e}")
            return ""

    @abstractmethod
    def execute(self, *args, **kwargs) -> Any:
        pass

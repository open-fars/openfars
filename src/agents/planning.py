from src.agents.base import BaseAgent
import json

class PlanningAgent(BaseAgent):
    def execute(self, idea: dict) -> dict:
        print("Planning Agent: Creating experiment plan...")
        
        prompt = f"""
        Given the following research idea:
        Title: {idea.get('title')}
        Hypothesis: {idea.get('hypothesis')}
        Methodology: {idea.get('methodology_sketch')}
        
        Create a detailed experiment plan.
        Provide the output in JSON format with:
        - steps: List of steps to execute
        - requirements: List of required libraries/resources
        - metrics: Metrics to evaluate success
        """
        
        response = self.call_llm(prompt, system_prompt="You are a senior research engineer responsible for planning experiments.")
        
        try:
            clean_response = response.replace("```json", "").replace("```", "").strip()
            if not clean_response: raise ValueError("Empty response")
            plan = json.loads(clean_response)
        except (json.JSONDecodeError, ValueError):
            plan = {
                "steps": ["Setup environment", "Run baseline", "Run proposed method", "Compare results"],
                "requirements": ["python", "pytorch"],
                "metrics": ["accuracy", "latency"]
            }
            
        self.workspace.save_metadata("plan", plan)
        print("Planning Agent: Plan created.")
        return plan

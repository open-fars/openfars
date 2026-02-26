from src.agents.base import BaseAgent
import json

class IdeationAgent(BaseAgent):
    def execute(self, research_topics: list[str]) -> dict:
        print("Ideation Agent: Generating research hypotheses...")
        
        prompt = f"""
        Based on the following research topics: {', '.join(research_topics)}
        Generate a novel research hypothesis for an AI paper.
        Provide the output in JSON format with the following fields:
        - title: Title of the proposed paper
        - hypothesis: The core hypothesis
        - motivation: Why this is important
        - methodology_sketch: Brief idea of how to test it
        """
        
        response = self.call_llm(prompt, system_prompt="You are an expert AI researcher responsible for generating novel research ideas.")
        
        try:
            clean_response = response.replace("```json", "").replace("```", "").strip()
            if not clean_response: raise ValueError("Empty response")
            idea = json.loads(clean_response)
        except (json.JSONDecodeError, ValueError):
            idea = {
                "title": f"Automated Research on {research_topics[0]}",
                "hypothesis": "AI agents can autonomously conduct research.",
                "motivation": "To scale science.",
                "methodology_sketch": "Build a multi-agent system."
            }
            
        self.workspace.save_metadata("idea", idea)
        print(f"Ideation Agent: Generated idea '{idea.get('title')}'")
        return idea

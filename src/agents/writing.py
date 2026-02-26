from src.agents.base import BaseAgent

class WritingAgent(BaseAgent):
    def execute(self, idea: dict, plan: dict, results: dict) -> str:
        print("Writing Agent: Writing paper...")
        
        prompt = f"""
        Write a short research paper based on the following:
        
        Title: {idea.get('title')}
        Hypothesis: {idea.get('hypothesis')}
        
        Experiment Plan:
        {plan}
        
        Results:
        {results}
        
        The paper should include: Abstract, Introduction, Methods, Results, Discussion.
        """
        
        paper_content = self.call_llm(prompt, system_prompt="You are an academic writer. Write a clear and concise research paper.")
        
        if not paper_content or "Mock LLM Response" in paper_content:
             paper_content = f"# {idea.get('title')}\n\n## Abstract\nThis is a generated paper about {idea.get('hypothesis')}.\n\n## Results\nWe achieved accuracy of {results.get('accuracy')}."

        filename = "paper.md"
        self.workspace.write_file(f"paper/{filename}", paper_content)
        print(f"Writing Agent: Paper written to {filename}")
        return paper_content

from src.agents.base import BaseAgent
import time
import random

class ExperimentAgent(BaseAgent):
    def execute(self, plan: dict) -> dict:
        print("Experiment Agent: Running experiments...")
        
        # This agent would normally interact with a GPU cluster and run actual code.
        # Here we simulate the execution.
        
        results = {}
        for step in plan.get("steps", []):
            print(f"  - Executing step: {step}")
            time.sleep(1) # Simulate work
            
            # Simulate generating code and running it
            code_filename = f"step_{step.lower().replace(' ', '_')[:20]}.py"
            code_content = f"# Implementation for {step}\nprint('Running {step}')"
            self.workspace.write_file(f"code/{code_filename}", code_content)
            
        # Simulate gathering results
        results = {
            "accuracy": 0.85 + random.random() * 0.1,
            "latency_ms": 100 + random.random() * 50,
            "success": True
        }
        
        self.workspace.save_metadata("results", results)
        print("Experiment Agent: Experiments completed.")
        return results

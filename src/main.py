import argparse
import uuid
import sys
import os

# Ensure src is in path if running directly
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.core.config import Config
from src.core.workspace import Workspace
from src.agents.ideation import IdeationAgent
from src.agents.planning import PlanningAgent
from src.agents.experiment import ExperimentAgent
from src.agents.writing import WritingAgent

def main():
    parser = argparse.ArgumentParser(description="FARS: Fully Automated Research System")
    parser.add_argument("--topics", nargs="+", default=["Reinforcement Learning"], help="List of research topics")
    parser.add_argument("--project-id", type=str, default=None, help="Project ID (default: auto-generated)")
    args = parser.parse_args()
    
    # Initialize
    Config.ensure_workspace()
    project_id = args.project_id or f"project_{uuid.uuid4().hex[:8]}"
    print(f"Starting FARS Project: {project_id}")
    
    workspace = Workspace(project_id)
    
    # Initialize Agents
    ideation_agent = IdeationAgent(workspace)
    planning_agent = PlanningAgent(workspace)
    experiment_agent = ExperimentAgent(workspace)
    writing_agent = WritingAgent(workspace)
    
    # 1. Ideation
    idea = ideation_agent.execute(args.topics)
    
    # 2. Planning
    plan = planning_agent.execute(idea)
    
    # 3. Experiment
    results = experiment_agent.execute(plan)
    
    # 4. Writing
    paper = writing_agent.execute(idea, plan, results)
    
    print(f"\nResearch workflow completed! Paper saved in workspace/{project_id}/paper/paper.md")

if __name__ == "__main__":
    main()

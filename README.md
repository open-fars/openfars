# OpenFARS: Open Source Fully Automated Research System

This is an open-source implementation of FARS (Fully Automated Research System), inspired by [Analemma's FARS](https://analemma.ai/fars).

FARS is designed to autonomously perform the complete research workflow—including ideation, planning, experimentation, and paper writing—without human intervention during execution.

## Features

- **Ideation Agent**: Generates novel research hypotheses.
- **Planning Agent**: Creates detailed experiment plans.
- **Experiment Agent**: Executes experiments (currently simulated).
- **Writing Agent**: Drafts research papers based on results.
- **Shared Workspace**: A persistent file system for agent collaboration.

## Getting Started

### Prerequisites

- Python 3.8+
- OpenAI API Key (for LLM capabilities)

### Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/openfars/openfars.git
   cd openfars
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Set up your OpenAI API key:
   ```bash
   export OPENAI_API_KEY="your-api-key-here"
   ```

### Usage

Run the system with a specific research topic:

```bash
python run.py --topics "Reinforcement Learning" "Large Language Models"
```

The system will generate a project ID and store all artifacts (plans, code, results, paper) in the `workspace/` directory.

## Project Structure

- `src/core`: Core configuration and shared workspace logic.
- `src/agents`: Implementation of the four specialized agents.
- `src/main.py`: Main orchestrator script.
- `workspace/`: Directory where research projects are stored.

## License

MIT License

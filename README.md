<h1 align="center">
    <img src="asset/stepfly_logo_v2.png" width="45" /> StepFly
</h1>

<div align="center">

<a href="https://deepwiki.com/microsoft/StepFly"><img src="https://devin.ai/assets/deepwiki-badge.png" alt="Ask DeepWiki.com" style="height:20px;"></a>
![Python Version](https://img.shields.io/badge/Python-3776AB?&logo=python&logoColor=white-blue&label=3.10%20%7C%203.11)&ensp;
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)&ensp;
![Welcome](https://img.shields.io/badge/contributions-welcome-brightgreen.svg?style=flat)

</div>

StepFly is an **agentic troubleshooting guide (TSG) automation framework** for intelligent incident diagnosis. This framework automatically executes troubleshooting procedures by coordinating multiple LLM agents, enabling efficient and systematic incident resolution guided by structured troubleshooting knowledge.

Unlike traditional manual troubleshooting that relies heavily on engineer expertise, StepFly preserves institutional knowledge in TSG documents and automates their execution through LLM agents. The framework features a **Scheduler-Executor architecture** where the Scheduler orchestrates the overall troubleshooting workflow based on a PlanDAG (Directed Acyclic Graph), while Executors perform individual diagnostic steps with various tools and plugins.

<h1 align="center">
    <img src="asset/stepfly.png" alt="StepFly Architecture"/> 
</h1>


## 💥 Highlights

- [x] **Automated TSG execution** - StepFly automatically executes troubleshooting guides with minimal human intervention, improving incident response efficiency.
- [x] **Multi-agent architecture** - A Scheduler agent orchestrates the workflow while multiple Executor agents perform diagnostic tasks in parallel.
- [x] **DAG-based workflow** - Troubleshooting steps are organized as a Directed Acyclic Graph (PlanDAG) enabling complex conditional logic and parallel execution.
- [x] **Plugin system** - Extensible plugin architecture allowing custom diagnostic tools to be seamlessly integrated from TSG documents.
- [x] **Memory and context management** - Persistent memory for sharing data between agents and maintaining troubleshooting context.
- [x] **Web-based monitoring** - Real-time visualization for monitoring agent activities and troubleshooting progress.

## 📁 Project Structure

Important directories and files in the StepFly project:
```
StepFly/
├── stepfly/                     # Core library
│   ├── agents/                  # Agent implementations
│   ├── tools/                   # Tool implementations
│   ├── prompts/                 # Agent prompts
├── config/                      # User configuration
│   ├── config.json              # Main config (user-specific)
│   └── incident_tsg_map.json    # Incident-TSG mapping
├── TSGs/                        # Troubleshooting Guides
│   └── PlanDAGs/                # Generated PlanDAG files
├── plugins/                     # QPP plugins
├── run_terminal.py              # CLI launcher
└── run_web.py                   # Web launcher
```

## ✨ Quick Start

### 🛠️ Step 1: Installation

StepFly requires **Python >= 3.10** and **MongoDB**. It can be installed by running the following commands:

```bash
# Clone the repository
git clone https://github.com/microsoft/StepFly.git
cd StepFly

# [Optional] Create conda environment
# conda create -n stepfly python=3.10
# conda activate stepfly

# Install the requirements
pip install -r requirements.txt
```

### 🖊️ Step 2: Configure LLM and Database

Before running StepFly, you need to configure your LLM API and MongoDB connection.

#### Configure LLM API

Configure in the configuration file:

```bash
# Configure in config/config.json
"llm": {
    "api_base": "",
    "api_key": "",
    "model": ""
}
```

💡 **Note**: Environment variables take precedence over config file. StepFly supports any LLM provider compatible with OpenAI API format.

#### Start MongoDB

```bash
# Option 1: Use the provided script to start MongoDB in Docker
./mongodb-docker.sh start
   
# Option 2: Use Docker Compose
docker-compose up -d

# Option 3: Install MongoDB locally and start the service
# See MongoDB installation guide for your OS
```

### 🚩 Step 3: Start StepFly

#### 💻 Web Dashboard

StepFly provides a web-based dashboard for visual monitoring of troubleshooting sessions:

```bash
# Start the web interface (browser will open automatically)
python run_web.py

# Or manually specify port and host
python ui/web_ui_run.py --port 8080 --host 0.0.0.0
```

Then open http://localhost:8080 in your browser to access the dashboard. First, create a new troubleshooting session by clicking the "Start Session" button and entering an incident ID. The dashboard will visualize the PlanDAG execution in real-time. You can click on individual nodes to view detailed Executor context and analysis.

<h1 align="left">
    <img src="asset/dashboard.png" alt="StepFly Dashboard"/> 
</h1>

#### ⌨️ Command Line Interface (CLI)

```bash
# Start the terminal interface
python run_terminal.py

# Or with a specific incident ID
python ui/terminal_ui.py --incident-id <INCIDENT_ID>
```

This will start StepFly and you can interact with it through the command line interface.

If everything goes well, you will see the following prompt:

```
╭────────── TSG Executor ──────────╮
│     Online Mode                  │
│ This mode helps you troubleshoot │
│ incidents using existing TSG     │
│ knowledge.                       │
╰──────────────────────────────────╯

Starting new troubleshooting session...
```

## 🎬 A Synthetic Demo

⚠️ **Warning**: All data used in this demo is synthetic and generated for demonstration purposes only.

### Diagnosing API Gateway Availability Drop (Incident 700000001)

This demo demonstrates how StepFly diagnoses a critical API gateway incident where availability dropped to 96.2% (below 99.9% SLA) across multiple regions. The root cause is hidden in a critical payment processing workflow failure that only manifests under specific business scenarios.

The troubleshooting process systematically checks service versions, feature flags, regional health, partitions, components, products, and finally discovers the critical workflow failure through business scenario analysis.

**Setup**: First generate the demo database following instructions in `demo_data/README.md`:
```bash
python demo_data/generate_distributed_system_data.py
```
This will create `demo_data/distributed_system.db` containing synthetic system metrics and logs.

**Run Demo (Web UI - Recommended)**:
```bash
# Start the web interface
python run_web.py

# In the web dashboard:
# 1. Click "Start Session" button
# 2. In the left sidebar Scheduler dialog, input incident ID: 700000001
# 3. Watch the PlanDAG visualization load and execute
# 4. Click on individual nodes to view real-time Executor context and analysis
# 5. Observe how the system systematically identifies the root cause in Step 9
```

For demo purposes, the mapping between incident IDs and TSGs is pre-configured in `config/incident_tsg_map.json`. The PlanDAGs for different TSGs are stored in `TSGs/PlanDAGs/`. We provide two versions of the same TSG: one for running in series and one for parallel execution. The default is the parallel version, and you can change it in the mapping file if needed. You can tune `max_executor_number` in `config/config.json` to control parallelism.

Annimation of the DAG execution:
![gif of demo](asset/stepfly.gif)

**Alternative (Terminal UI)**:
```bash
python run_terminal.py
# Follow prompts and enter incident ID: 700000001
```

## 🔧 Creating Custom TSGs

To create a new troubleshooting guide, follow this guide: [Creating Custom TSGs](./TSGs/README.md)

## 📚 Citation

If you use [StepFly](https://arxiv.org/abs/2510.10074) in your research, please cite:

```
@misc{stepfly2025,
      title={Agentic Troubleshooting Guide Automation for Incident Management}, 
      author={Jiayi Mao and Liqun Li and Yanjie Gao and Zegang Peng and Shilin He and Chaoyun Zhang and Si Qin and Samia Khalid and Qingwei Lin and Saravan Rajmohan and Sitaram Lanka and Dongmei Zhang},
      year={2025},
      eprint={2510.10074},
      archivePrefix={arXiv},
      url={https://arxiv.org/abs/2510.10074}, 
}
```

📌 **Note**: Full citation information will be updated upon publication.

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.


## ⚠️ Disclaimer

**Warning**: StepFly is a research prototype and should be tested thoroughly before use in production environments. The recommended LLM models are examples for exploring agent capabilities. Users are responsible for complying with the licenses of third-party models and services they choose to use with StepFly.


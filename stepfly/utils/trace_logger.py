import os
import json
import datetime
from typing import List, Dict, Any, Optional

def save_agent_trace(agent_type: str, agent_id: str, data: Dict[str, Any], session_id: str) -> str:
    trace_dir = os.path.join(os.getcwd(), "trace", session_id)
    os.makedirs(trace_dir, exist_ok=True)

    # Create agent-specific subdirectory
    agent_dir = os.path.join(trace_dir, agent_type)
    os.makedirs(agent_dir, exist_ok=True)
    
    # Create file path for this agent
    file_path = os.path.join(agent_dir, f"{agent_id}.json")
    
    # Save data to file
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    print(f"Agent trace updated in: {file_path}")
    return file_path

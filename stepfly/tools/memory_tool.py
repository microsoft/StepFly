import json

import pandas as pd

from stepfly.utils.memory import Memory
from stepfly.tools.base_tool import BaseTool


class MemoryTool(BaseTool):
    """Read-only tool for accessing information from the shared memory used by multiple agents."""
    
    def __init__(self, session_id: str, memory: Memory):
        super().__init__(session_id, memory)
        self.name="memory_tool"
        self.description=(
            "Read-only tool for accessing information from the shared memory used by multiple agents.\n\n"
            "Required Parameters:\n"
            "- action: Action to perform (get_data, list_data, get_data_summary, get_data_section, search_data, get_code_snippet)\n\n"
            "Optional Parameters (action-specific):\n"
            "- data_id: UUID of the data to access\n"
            "- data_type: Filter by data type\n"
            "- agent_id: Filter by agent ID\n"
            "- start_line: Starting line/row (default: 0)\n"
            "- num_lines: Number of lines/rows (default: 20)\n"
            "- search_term: Text to search for\n"
            "- snippet_id: ID of the code snippet"
        )
    
    def execute(self, action: str, **kwargs) -> str:
        """
        Execute an action in the shared memory (read-only)
        
        Args:
            action: Action to perform
            **kwargs: Action-specific parameters
            
        Returns:
            Result of the action
        """
        try:
            # Only allow read-only actions
            if action in ["get_data", "list_data", "get_data_summary", 
                         "get_data_section", "search_data", "get_code_snippet"]:
                
                if action == "get_data":
                    data_id = kwargs.get("data_id")
                    if not data_id:
                        return "Error: data_id parameter is required"
                        
                    data = self.memory.get_data(data_id)
                    if data is None:
                        return f"No data found with ID: {data_id}"
                    
                    # Special handling for DataFrames
                    if isinstance(data, pd.DataFrame):
                        # For large DataFrames, return a summary view
                        if data.shape[0] > 10:
                            result = f"DataFrame with shape {data.shape}, columns: {list(data.columns)}\n\n"
                            result += "First 5 rows:\n"
                            result += data.head(5).to_string()
                            result += "\n\nUse code_interpreter tool to analyze this DataFrame efficiently."
                            return result
                        else:
                            # For small DataFrames, return the complete view
                            return data.to_string()
                    
                    # Handle other data types
                    if isinstance(data, (dict, list)):
                        return json.dumps(data, indent=2)
                    return str(data)
                    
                elif action == "list_data":
                    data_type = kwargs.get("data_type")
                    agent_id = kwargs.get("agent_id")
                    return self.memory.list_data(data_type=data_type, agent_id=agent_id)
                    
                elif action == "get_data_summary":
                    data_id = kwargs.get("data_id")
                    if not data_id:
                        return "Error: data_id parameter is required"
                        
                    return self.memory.get_data_summary(data_id)
                    
                elif action == "get_data_section":
                    data_id = kwargs.get("data_id")
                    start_line = int(kwargs.get("start_line", 0))
                    num_lines = int(kwargs.get("num_lines", 20))
                    
                    if not data_id:
                        return "Error: data_id parameter is required"
                        
                    return self.memory.get_data_section(data_id, start_line, num_lines)
                    
                elif action == "search_data":
                    data_id = kwargs.get("data_id")
                    search_term = kwargs.get("search_term")
                    
                    if not data_id:
                        return "Error: data_id parameter is required"
                    if not search_term:
                        return "Error: search_term parameter is required"
                        
                    return self.memory.search_data(data_id, search_term)
                    
                elif action == "get_code_snippet":
                    snippet_id = kwargs.get("snippet_id")
                    if not snippet_id:
                        return "Error: snippet_id parameter is required"
                    
                    code = self.memory.get_code_snippet(snippet_id)
                    if code:
                        return f"```\n{code}\n```"
                    else:
                        return f"Error: Code snippet with ID {snippet_id} not found"
                    
            else:
                return f"Error: Action '{action}' not allowed or not found. This is a read-only tool."
                
        except Exception as e:
            return f"Error executing memory action: {str(e)}" 
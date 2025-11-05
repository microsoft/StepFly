from typing import Optional

from stepfly.utils.memory import Memory
from stepfly.tools.base_tool import BaseTool


class LogReasoningTool(BaseTool):
    """Tool for logging reasoning process without executing complex operations"""
    
    def __init__(self, session_id: str, memory: Memory):
        super().__init__(session_id, memory)
        self.name="log_reasoning_tool"
        self.description=(
            "Log the reasoning process when only reasoning is needed for the action. Use this tool "
            "instead of complex tools like code_interpreter when you only need to analyze, extract, "
            "or reason about data without performing computations.\n\n"

            "## Purpose\n"
            "- Document thought processes for transparency\n"
            "- Record analytical insights without computation\n"
            "- Extract information from previous tool outputs\n"
            "- Make logical deductions from available data\n\n"

            "## Optional Parameters\n"
            "- **reasoning** (string): Explanation of your reasoning process\n"
            "- **observation** (string): Observation about the data or situation\n\n"

            "## When to Use\n"
            "- When extracting information from previous tool outputs\n"
            "- When analyzing data patterns without computation\n"
            "- When making logical deductions from available information\n"
            "- When documenting thought process for transparency\n"
            "- When simple reasoning is sufficient without code execution\n\n"

            "## Usage Examples\n"
            "**Reasoning with observation:**\n"
            "```json\n"
            "{\n"
            "  \"reasoning\": \"Based on the incident details, I need to check deployment status around the incident time\",\n"
            "  \"observation\": \"The incident started at 2024-01-01T10:30:00Z, so I should check deployments 2 hours before\"\n"
            "}\n"
            "```\n\n"
            "**Simple reasoning:**\n"
            "```json\n"
            "{\n"
            "  \"reasoning\": \"Analyzing the query results shows a clear correlation between deployment and errors\"\n"
            "}\n"
            "```\n\n"

            "## Notes\n"
            "- **Alternative to Code**: Use instead of code_interpreter for simple analysis\n"
        )
    
    def execute(self, 
                reasoning: Optional[str] = None,
                observation: Optional[str] = None) -> str:
        """
        Log the reasoning process without executing any actions
        
        Args:
            reasoning: Optional explanation of the reasoning process
            observation: Optional observation about the data
            
        Returns:
            Acknowledgment of the logged reasoning
        """
        # Prepare the response message
        response = "Reasoning process logged successfully.\n\n"
        
        if reasoning:
            response += f"Reasoning: {reasoning}\n\n"
        
        if observation:
            response += f"Observation: {observation}\n\n"
        
        if not reasoning and not observation:
            response += "No specific reasoning or observations provided."
        
        return response 
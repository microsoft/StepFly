from stepfly.utils.memory import Memory
from stepfly.tools.base_tool import BaseTool

class FinishStepTool(BaseTool):
    """Tool for finishing step execution with result and edge status updates"""
    
    def __init__(self, session_id: str, memory: Memory):
        super().__init__(session_id, memory)
        self.name="finish_step"
        self.description=(
            "Mark the current step as complete and provide structured output with result and edge status updates. "
            "This tool is used to conclude step execution and specify which output edges should be enabled or disabled.\n\n"

            "## Purpose\n"
            "- Conclude current step execution with structured results\n"
            "- Enable conditional workflow progression\n\n"

            "## Required Parameters\n"
            "- **result** (string): Detailed summary of your observations, findings, and conclusions from this step\n"
            "- **status** (string): Status of the step, should be 'completed' or 'failed'\n"
            "- **set_edge_status** (dict): Dictionary mapping edge names to their new status ('enabled' or 'disabled')\n\n"

            "## Edge Status Guidelines\n"
            "- **Enable an edge**: When the condition for that path is met and you want the connected step to execute\n"
            "- **Disable an edge**: When the condition is NOT met or you want to skip the connected step\n"
            "- **Unconditional edges**: Usually enable them unless there's a specific reason to stop\n"
            "- **Conditional edges**: Enable only when the specific condition is satisfied\n\n"
            "- **Step Failures**: If the step fails, you must disable all edges to prevent further execution\n\n"

            "## Usage Examples\n"
            "**Conditional workflow completion:**\n"
            "```json\n"
            "{\n"
            "  \"result\": \"Service availability analysis completed. Found 95% availability exceeding 90% threshold.\",\n"
            "  \"status\": \"completed\",\n"
            "  \"set_edge_status\": {\n"
            "    \"edge_s2_investigation\": \"disabled\",\n"
            "    \"edge_s2_conclusion\": \"enabled\"\n"
            "  }\n"
            "}\n"
            "```\n\n"
            "**Error handling and fallback:**\n"
            "```json\n"
            "{\n"
            "  \"result\": \"Service availability analysis failed due to timeout.\",\n"
            "  \"status\": \"failed\",\n"
            "  \"set_edge_status\": {\n"
            "    \"edge_s2_investigation\": \"disabled\",\n"
            "    \"edge_s2_conclusion\": \"disabled\"\n"
            " }\n"
        )
    
    def execute(self, result: str, set_edge_status: dict) -> str:
        """
        Mark step as complete with result and edge status updates
        
        Args:
            result: Summary of findings and conclusions
            set_edge_status: Dictionary of edge name -> status mappings
            
        Returns:
            Confirmation message
        """
        # Validate parameters
        if not result or not isinstance(result, str):
            return "Error: 'result' parameter must be a non-empty string"
        
        if not set_edge_status or not isinstance(set_edge_status, dict):
            return "Error: 'set_edge_status' parameter must be a dictionary"
        
        # Validate edge status values
        valid_statuses = {"enabled", "disabled"}
        for edge_name, status in set_edge_status.items():
            if status not in valid_statuses:
                return f"Error: Invalid status '{status}' for edge '{edge_name}'. Must be 'enabled' or 'disabled'"
        
        return f"Step completion confirmed. Result: {result[:100]}{'...' if len(result) > 100 else ''}. Edge updates: {len(set_edge_status)} edges." 
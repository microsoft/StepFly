import json
from typing import Dict, Any, List, Optional, Callable, Tuple
import re
import os
import importlib
import pkgutil
from rich.console import Console
from rich.panel import Panel
import datetime
from stepfly.utils.config_loader import config
from stepfly.utils.llm_client import LLMClient

from stepfly.utils.memory import Memory
from stepfly.utils.trace_logger import save_agent_trace

class BaseAgent:
    """
    Base class for all agents in the system.
    Provides common functionality like LLM interaction, output streaming, and tool loading.
    """
    
    def __init__(self, session_id: Optional[str] = None, memory: Memory = None):
        """
        Initialize the base agent
        
        Args:
            name: Name of the agent for logging purposes
        """
        self.role = ""
        self.agent_id = None  # Will be set
        self.name = "base_agent"
        self.console = Console()
        self.llm_client = LLMClient()
        self.memory = memory

        # Initialize token usage tracking with timing info
        self.token_usage = {
            "total_input_tokens": 0,
            "total_output_tokens": 0,
            "total_tokens": 0,
            "llm_calls_count": 0,
            "start_time": datetime.datetime.now().isoformat(),
            "end_time": None,
            "duration_seconds": 0,
            "last_updated": datetime.datetime.now().isoformat()
        }

        # Initialize session state
        self.session_state = {
            "session_id": session_id,
            "incident_info": {},
            "tsg_content": "",
            "complete": False,
            "steps_executed": 0,
            "current_observation": "",
            "execution_status": "initialized",
            "current_node": None,
            "variables": {},
            "current_tsg_name": None,
            "current_step": None,
            "incident_info_idx": -1
        }

        self.conversation_history = []

        
    def _load_tools(self, session_id: str, memory: Memory) -> Dict[str, Any]:
        """
        Load all available tools using dynamic loading
        Sets self.tools as a dictionary mapping tool names to tool instances.
        Also sets self.tools_description (string) for compatibility.
        
        Returns:
            Dictionary of tool instances
        """
        from stepfly.tools.base_tool import BaseTool
        
        tools_list = []
        
        # Try to import and load tools dynamically
        # Import the tools package
        import stepfly.tools as tools_package

        # Get all modules in the tools package
        for _, name, is_pkg in pkgutil.iter_modules(tools_package.__path__):
            if name != "base_tool" and not is_pkg:
                # Import the module
                module = importlib.import_module(f"stepfly.tools.{name}")

                # Find classes that inherit from BaseTool
                for attr_name in dir(module):
                    attr = getattr(module, attr_name)
                    if (isinstance(attr, type) and
                            issubclass(attr, BaseTool) and
                            attr is not BaseTool):
                        # Create an instance of the tool
                        tool = attr(session_id=session_id, memory=memory)
                        tools_list.append(tool)
        self.console.print("[green]Loaded tool:[/green]", ", ".join([tool.name for tool in tools_list]))

        # Set up unified dictionary structure
        tools_dict = {}
        for tool in tools_list:
            # Use the tool's actual name as the key
            tools_dict[tool.name] = tool
        
        # Filter tools based on agent role configuration
        filtered_tools = self._filter_tools_by_role(tools_dict)
        
        # Set the unified tools dictionary
        self.tools = filtered_tools
        
        # For backward compatibility and prompt building
        self.tools_description = "\n\n\n\n".join([
            tool.get_description() for tool in filtered_tools.values()
        ])
        
        return filtered_tools
    
    def _filter_tools_by_role(self, all_tools: Dict[str, Any]) -> Dict[str, Any]:
        """
        Filter tools based on the current agent's role configuration
        
        Args:
            all_tools: Dictionary of all available tools
            
        Returns:
            Dictionary of filtered tools based on role configuration
        """
        # Get the role in lowercase for configuration key matching
        role_key = self.role.lower() if hasattr(self, 'role') and self.role else None
        
        # If no role is set, return all tools
        if not role_key:
            return all_tools
        
        # Get allowed tools from configuration
        allowed_tools = config.get(f"{role_key}.allowed_tools", [])
        
        # If no configuration found, return all tools (backward compatibility)
        if not allowed_tools:
            return all_tools
        
        # Filter tools based on configuration
        filtered_tools = {}
        for tool_name, tool_instance in all_tools.items():
            if tool_name in allowed_tools:
                filtered_tools[tool_name] = tool_instance
        
        # Log the filtering result
        if filtered_tools != all_tools:
            filtered_count = len(filtered_tools)
            total_count = len(all_tools)
            filtered_names = list(filtered_tools.keys())
            self.console.print(f"[blue]Filtered tools for {self.role}:[/blue] {filtered_count}/{total_count} tools loaded")
            # self.console.print(f"[green]Allowed tools:[/green] {', '.join(filtered_names)}")
        
        return filtered_tools
    
    def _update_token_usage(self, usage_info: Dict[str, int]) -> None:
        """
        Update token usage statistics
        
        Args:
            usage_info: Dictionary containing input_tokens, output_tokens, total_tokens
        """
        self.token_usage["total_input_tokens"] += usage_info.get("input_tokens", 0)
        self.token_usage["total_output_tokens"] += usage_info.get("output_tokens", 0) 
        self.token_usage["total_tokens"] += usage_info.get("total_tokens", 0)
        self.token_usage["llm_calls_count"] += 1
        self.token_usage["last_updated"] = datetime.datetime.now().isoformat()
        
        # Auto-save token usage after each LLM call
        self._save_token_usage()
    
    def _save_token_usage(self) -> None:
        """
        Save token usage statistics to trace file
        """
        session_id = self.session_state.get("session_id")
        if not session_id:
            print("Warning: session_id not set, cannot save token usage")
            return
            
        # Use the same trace directory structure as save_agent_trace
        trace_dir = os.path.join(os.getcwd(), "trace", session_id)
        os.makedirs(trace_dir, exist_ok=True)
        
        token_usage_file = os.path.join(trace_dir, "token_time_usage.json")
        
        # Load existing data if file exists
        existing_data = {}
        if os.path.exists(token_usage_file):
            with open(token_usage_file, 'r', encoding='utf-8') as f:
                existing_data = json.load(f)
        
        # Update with current agent's token usage including timing
        agent_key = f"{self.role}_{self.agent_id}" if self.agent_id else self.role
        current_usage = self.token_usage.copy()
        
        # Update end time and duration
        current_usage["end_time"] = datetime.datetime.now().isoformat()
        if current_usage.get("start_time"):
            start = datetime.datetime.fromisoformat(current_usage["start_time"])
            end = datetime.datetime.fromisoformat(current_usage["end_time"])
            duration = (end - start).total_seconds()
            current_usage["duration_seconds"] = duration
        
        existing_data[agent_key] = current_usage
        
        # Calculate session totals
        session_totals = {
            "session_total_input_tokens": sum(agent_data.get("total_input_tokens", 0) for key, agent_data in existing_data.items() if isinstance(agent_data, dict) and key != "session_totals"),
            "session_total_output_tokens": sum(agent_data.get("total_output_tokens", 0) for key, agent_data in existing_data.items() if isinstance(agent_data, dict) and key != "session_totals"),
            "session_total_tokens": sum(agent_data.get("total_tokens", 0) for key, agent_data in existing_data.items() if isinstance(agent_data, dict) and key != "session_totals"),
            "session_total_llm_calls": sum(agent_data.get("llm_calls_count", 0) for key, agent_data in existing_data.items() if isinstance(agent_data, dict) and key != "session_totals"),
            "last_updated": datetime.datetime.now().isoformat()
        }
        
        # Calculate simple metrics for all executors and code_generator (excluding scheduler)
        executor_agents = [(key, agent_data) for key, agent_data in existing_data.items() 
                          if isinstance(agent_data, dict) and (key.startswith("Executor_") or key == "code_generator") and key != "session_totals"]
        
        if executor_agents:
            # Calculate totals for all executors and code_generator
            session_totals["total_executor_input_tokens"] = sum(
                agent_data.get("total_input_tokens", 0) for _, agent_data in executor_agents
            )
            session_totals["total_executor_output_tokens"] = sum(
                agent_data.get("total_output_tokens", 0) for _, agent_data in executor_agents
            )
            session_totals["total_executor_total_tokens"] = sum(
                agent_data.get("total_tokens", 0) for _, agent_data in executor_agents
            )
            session_totals["total_executor_llm_calls"] = sum(
                agent_data.get("llm_calls_count", 0) for _, agent_data in executor_agents
            )
            
            # Calculate total executor duration (from earliest start to latest end)
            try:
                start_times = [agent_data.get("start_time") for _, agent_data in executor_agents if agent_data.get("start_time")]
                end_times = [agent_data.get("end_time") for _, agent_data in executor_agents if agent_data.get("end_time")]
                
                if start_times and end_times:
                    earliest_start = min(start_times)
                    latest_end = max(end_times)
                    
                    first_start = datetime.datetime.fromisoformat(earliest_start)
                    last_end = datetime.datetime.fromisoformat(latest_end)
                    duration = (last_end - first_start).total_seconds()
                    
                    session_totals["total_executor_duration_seconds"] = duration
                    session_totals["total_executor_duration_formatted"] = f"{int(duration//60)}m {int(duration%60)}s"
            except Exception:
                pass
        
        # Create ordered data with session_totals first
        ordered_data = {"session_totals": session_totals}
        # Add agent data in sorted order
        for key in sorted(existing_data.keys()):
            if key != "session_totals":  # Skip session_totals since we already added it
                ordered_data[key] = existing_data[key]
        
        # Save updated data with immediate flush
        with open(token_usage_file, 'w', encoding='utf-8') as f:
            json.dump(ordered_data, f, indent=2, ensure_ascii=False)
            f.flush()  # Ensure data is written to disk immediately
            os.fsync(f.fileno())  # Force write to disk

    def call_llm(self, messages: List[Dict[str, str]], stream: bool = True, json_response: bool = True) -> str:
        """
        Call LLM with the given messages and return the response
        
        Args:
            messages: List of message dictionaries with role and content
            stream: Whether to stream the output to console
            
        Returns:
            The full response text
        """
        return self._stream_llm_call(messages, json_response)

    def _stream_llm_call(self, messages: List[Dict[str, str]], json_response: bool) -> str:
        """
        Stream LLM call with real-time output to console
        
        Args:
            messages: List of message dictionaries
            
        Returns:
            The full response text
        """
        # Stream the response
        full_response = ""
        
        def stream_callback(content_chunk: str):
            nonlocal full_response
            full_response += content_chunk
            self.console.print(content_chunk, end="")
        
        response_text, usage_info = self.llm_client.stream_completion(
            messages=messages,
            callback=stream_callback,
            json_response=json_response
        )
        
        # Update token usage
        self._update_token_usage(usage_info)
        
        # Extra newline for better formatting
        self.console.print()
        
        return response_text
    
    def _record_response(self, response: str, prefix: Optional[str] = "") -> None:
        # Add to conversation history
        self.conversation_history.append({"role": "assistant", "content": response})
        self.register_conversation_message(self.agent_id, self.conversation_history[-1])

        # Save conversation history to trace
        save_agent_trace(
            session_id=self.session_state["session_id"],
            agent_type=self.role,
            agent_id=f"{prefix}_{self.agent_id}",
            data={
                "conversation_history": self.conversation_history,
                "session_state": self.session_state,
                "token_usage": self.token_usage
            }
        )

    def _record_observation(self, observation: str, prefix: Optional[str] = "") -> None:
        """
        Record the observation in the conversation history

        Args:
            observation: Result of the action
        """
        self.conversation_history.append({"role": "user", "content": f"Observation: {observation}"})
        self.register_conversation_message(self.agent_id, self.conversation_history[-1])
        self._display_observation(observation)

        # Save conversation history to trace
        save_agent_trace(
            session_id=self.session_state["session_id"],
            agent_type=self.role,
            agent_id=f"{prefix}_{self.agent_id}",
            data={
                "conversation_history": self.conversation_history,
                "session_state": self.session_state,
                "token_usage": self.token_usage
            }
        )
        
    def display_message(self, message: str, title: Optional[str] = None, style: str = "blue"):
        """
        Display a message in a styled panel
        
        Args:
            message: The message to display
            title: Optional title for the panel
            style: Border style color
        """
        panel_title = title or self.name.capitalize()
        self.console.print(Panel(message, title=panel_title, border_style=style))

    def _display_observation(self, observation: str) -> None:
        """
        Record the observation in the conversation history
        
        Args:
            observation: Result of the action
        """
        # Display observation summary (truncated if too long)
        max_display_length = 2000
        display_observation = observation
        if len(observation) > max_display_length:
            display_observation = observation[:max_display_length] + "... (truncated)"
        
        self.console.print(f"[bold yellow]Observation:[/bold yellow] {display_observation}")


    def register_conversation_message(self, agent_id: str, message: Dict[str, Any]) -> None:
        assert agent_id, "Agent ID must be set before registering messages"
        # Update agent context with conversation
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        self.memory.add_agent_context(
            agent_id=agent_id,
            key=f"message_{timestamp}",
            value=message,
            description=f"message at {timestamp}"
        )


    def _sanitize_filename(self, filename: str) -> str:
        """
        Sanitize a filename to ensure it's valid
        
        Args:
            filename: Original filename
            
        Returns:
            Sanitized filename
        """
        # Replace invalid characters with underscores
        invalid_chars = '<>:"/\\|?*'
        for char in invalid_chars:
            filename = filename.replace(char, '_')
        
        return filename
    
    def _extract_step_marker(self, text: str) -> Optional[int]:
        """
        Extract step number from text if a step marker is present
        
        Args:
            text: Text to search for step marker
            
        Returns:
            Step number or None if no marker is found
        """
        # Look for <STEP-X> pattern at the beginning of the text
        match = re.match(r'^\s*<STEP-(\d+)>', text)
        if match:
            return int(match.group(1))
        return None
    
    def _get_experiences_for_step(self, step: int) -> str:
        """
        Get experiences for a specific step from the saved experiences
        
        Args:
            step: Step number
            
        Returns:
            String containing relevant experiences
        """
        if not self.session_state["current_tsg_name"]:
            return ""
            
        tsg_name = self.session_state["current_tsg_name"]
        
        # Sanitize TSG name
        sanitized_tsg_name = self._sanitize_filename(tsg_name)
        
        # Path to the summarized experiences file
        exp_dir = os.path.join(os.getcwd(), "experience", sanitized_tsg_name)
        exp_file = os.path.join(exp_dir, "summarized_experiences.json")
        
        if not os.path.exists(exp_file):
            return ""
            
        try:
            with open(exp_file, 'r', encoding='utf-8') as f:
                experiences = json.load(f)
                
            # Get the topk most recent experiences
            topk = config.get("experience.topk", 3)
            
            if not isinstance(experiences, list):
                experiences = [experiences]
                
            # Sort by timestamp (most recent first)
            experiences.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
            
            # Take top k experiences
            relevant_experiences = []
            for exp in experiences[:topk]:
                step_key = f"step-{step}"
                if step_key in exp:
                    relevant_experiences.append(exp[step_key])
            
            if not relevant_experiences:
                return ""
                
            return "\n- " + "\n- ".join(relevant_experiences)
            
        except Exception as e:
            self.console.print(f"[yellow]Error loading experiences:[/yellow] {str(e)}")
            return ""


    def _format_conclusion_dict(self, conclusion_dict: Dict[str, Any]) -> str:
        """
        Format a dictionary conclusion into a readable string format
        
        Args:
            conclusion_dict: Dictionary containing conclusion components
            
        Returns:
            Formatted string representation of the conclusion
        """
        formatted_parts = []
        
        # Define the expected order and display names for conclusion components
        component_mapping = {
            "Incident Summary": "📋 Incident Summary",
            "Root Cause Analysis": "🔎 Root Cause Analysis", 
            "Key Findings": "🔍 Key Findings",
            "Resolution Status": "✅ Resolution Status",
            "Impact Assessment": "📊 Impact Assessment",
            "Lessons Learned": "📚 Lessons Learned",
            "Prevention Recommendations": "🛡️ Prevention Recommendations"
        }
        
        # Process components in the defined order
        for key, display_name in component_mapping.items():
            if key in conclusion_dict:
                value = conclusion_dict[key]
                formatted_parts.append(f"\n{display_name}:")
                
                if isinstance(value, list):
                    # Format list items
                    for i, item in enumerate(value, 1):
                        formatted_parts.append(f"  {i}. {item}")
                elif isinstance(value, str):
                    # Format string value with proper indentation
                    formatted_parts.append(f"  {value}")
                else:
                    # Convert other types to string
                    formatted_parts.append(f"  {str(value)}")
                
                formatted_parts.append("")  # Add spacing between sections
        
        # Add any additional keys that weren't in the mapping
        for key, value in conclusion_dict.items():
            if key not in component_mapping:
                formatted_parts.append(f"\n📌 {key}:")
                if isinstance(value, list):
                    for i, item in enumerate(value, 1):
                        formatted_parts.append(f"  {i}. {item}")
                elif isinstance(value, str):
                    formatted_parts.append(f"  {value}")
                else:
                    formatted_parts.append(f"  {str(value)}")
                formatted_parts.append("")
        
        return "\n".join(formatted_parts).strip()

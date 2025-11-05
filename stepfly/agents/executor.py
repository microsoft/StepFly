import datetime
import json
from typing import Dict, Any, Tuple

from stepfly.agents.base_agent import BaseAgent
from stepfly.utils.memory import Memory
from stepfly.utils.config_loader import config
from stepfly.prompts import Prompts
from stepfly.utils.trace_logger import save_agent_trace


class Executor(BaseAgent):
    """
    Executor agent that troubleshoots incidents using TSG documents.
    Implements the ReACT (Reasoning, Acting, and Observing) framework.
    """
    
    def __init__(self, session_id: str, memory: Memory, agent_id: str, step_name: str = "executor"):
        """Initialize the Executor agent"""
        super().__init__(session_id=session_id, memory=memory)
        self.step_name = step_name
        self.execution_state = None
        self.name = f"executor_{step_name}"
        self.role = "Executor"
        self.console.print(f"[bold green]Initializing Executor Agent:[/bold green] {self.name} @ {session_id}")
        
        # Register with memory using the provided agent_id
        self.agent_id = memory.register_agent(agent_name=self.name, agent_id=agent_id)
        # Load tools
        self._load_tools(session_id=self.session_state["session_id"], memory=self.memory)
        # Load TSG plugins
        self._preload_plugins_for_executor()
        
        # Add to memory
        self.memory.add_data(
            data=self.session_state,
            data_type="executor_state",
            agent_id=self.agent_id,
            description=f"Executor {self.agent_id} state",
            metadata={"key": f"executor_{self.agent_id}_state"}
        )

    def _preload_plugins_for_executor(self) -> None:
        import re
        
        # Check if plugins are enabled in configuration
        enable_plugins = config.get("tools.enable_plugins", True)
        if not enable_plugins:
            self.console.print("[yellow]Plugins are disabled in configuration. Skipping plugin loading.[/yellow]")
            return

        # Get TSG content from memory
        tsg_content = self.memory.get_data_by_key("tsg_content")
        if not tsg_content:
            raise FileNotFoundError("TSG content not found in memory. Please run tsg_loader tool first.")

        # Check for plugin marker in TSG content
        plugin_marker = re.search(r'<!-- TSG_PLUGINS:([^\s]+) -->', tsg_content)
        if not plugin_marker:
            raise ValueError(
                "No plugin marker found in TSG content. Please ensure the TSG document contains a valid plugin marker.")

        # Get the TSG name from the marker
        tsg_name = plugin_marker.group(1)
        self.console.print(f"[bold green]Pre-loading plugins for executor with TSG:[/bold green] {tsg_name}")

        # Import BasePlugin class
        from plugins.base_plugin import BasePlugin

        # Get all plugins for this TSG
        plugins = BasePlugin.get_plugins_for_tsg(tsg_name)

        if not plugins:
            raise ValueError(
                f"No plugins found for TSG: {tsg_name}. Please ensure the TSG document is correctly configured with plugins.")

        # Create tools from plugins and add to executor
        new_tools = []
        tool_descriptions = []

        for plugin in plugins:
            tool_name = f"{plugin.plugin_id}_tool"

            # Skip if executor already has this tool
            if tool_name in self.tools:
                raise ValueError(
                    f"Tool '{tool_name}' already exists in executor. Please check your TSG configuration.")

            # Create a tool from the plugin
            plugin_tool = BasePlugin.create_tool_from_plugin(
                plugin,
                session_id=self.session_state["session_id"],
                memory=self.memory
            )

            # Add tool to executor's available tools dictionary
            self.tools[tool_name] = plugin_tool
            new_tools.append(plugin_tool)

            # Build tool description for prompt update
            tool_descriptions.append(f"{tool_name}: {plugin.description} [Language: {plugin.language}]")

        self.console.print(f"[green]Pre-loaded plugin tool for executor:[/green]",
                           ", ".join([tool.name for tool in new_tools]),
                           "for session:", self.session_state["session_id"])

        self.console.print(f"[green]Successfully pre-loaded {len(new_tools)} plugin tools for executor[/green]")

    def _execute_action(self, action: str, parameters: Dict[str, Any]) -> str:
        # Check for empty action (e.g., when session is complete)
        if not action:
            return "No action to execute. Continuing with the session."
        
        # Look for the tool - use direct lookup first, then case-insensitive search
        tool = self.tools.get(action)
        if not tool:
            # Fallback: case-insensitive search
            for tool_name, tool_instance in self.tools.items():
                if tool_name.lower() == action.lower():
                    tool = tool_instance
                    break
        
        if not tool:
            return f"Error: Tool '{action}' not found. Available tools: {', '.join(self.tools.keys())}"
        
        # Log the execution attempt
        self.display_message(f"Executing: {action}", style="blue")
        
        # Execute the tool
        try:
            result = tool.execute(**parameters)
            return result
        except Exception as e:
            error_message = f"Error executing {action}: {str(e)}"
            self.display_message(error_message, style="red")
            return error_message

    def execute_step(self, context: str, max_retry_number: int = 3) -> Dict[str, Any]:
        # Create step node structure
        self.execution_state = {
            "step_name": self.step_name,
            "status": "running",
            "start_time": datetime.datetime.now().isoformat(),
            "context": context
        }

        # Display start message
        self.display_message(f"Executing step: {self.step_name}", title="Step Execution")

        system_prompt = Prompts.step_executor_system_prompt(self.tools_description, max_retry_number=max_retry_number)
        
        # Reset conversation history for this step
        self.conversation_history = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"# Step: {self.step_name}\n\n{context}\n\nExecute this step and provide a clear result. "
                                        f"Focus on specific findings and conclusions."}
        ]
        
        for message in self.conversation_history:
            self.register_conversation_message(self.agent_id, message)
        
        save_agent_trace(
            session_id=self.session_state["session_id"],
            agent_type=self.role,
            agent_id=f"{self.step_name}_{self.agent_id}",  # Use step_name instead of node_id
            data={
                "conversation_history": self.conversation_history,
                "step_info": {
                    "name": self.step_name,
                    "context": context
                },
                "execution_state": self.execution_state,
                "status": "initialized"
            }
        )
    
        max_iterations = config.get("executor.max_iterations", 10)
        step_result = None
        step_status = "running"
        set_edge_status = {}  # Store edge status updates
        current_inter = 1 # Track current iteration for incremental trace saving

        while current_inter < max_iterations:
            # **INCREMENTAL TRACE SAVE**: Save trace after each iteration
            # Update execution state with iteration info
            self.execution_state.update({"current_iteration": current_inter})

            # Get agent's next action
            if self.step_name.lower() == "end":
                self.console.print(f"[blue]Iteration {current_inter} - Ending step execution as step is 'end'[/blue]")
                json_data = {
                    "thought": "No further actions required. Ending step execution.",
                    "action": "finish_step",
                    "parameters": {
                        "result": "The full TSG execution completed",
                        "status": "completed",
                        "set_edge_status": {}
                    }
                }
                response = json.dumps(json_data)
            else:
                self.console.print(f"[blue]Iteration {current_inter} - Calling LLM for next action...[/blue]")
                retry_count = 0
                response = ""  
                for retry in range(max_retry_number):
                    try:
                        response = self.call_llm(self.conversation_history)
                        # Parse response to extract thought, action, and parameters
                        if response.startswith("```json"):
                            response = response[7:]
                        if response.endswith("```"):
                            response = response[:-3]
                        json_data = json.loads(response)
                        break
                    except json.JSONDecodeError as e:
                        self.console.print(f"[red]Error decoding JSON response from LLM: {response}[/red]")
                        retry_count += 1
                        if retry_count >= max_retry_number:
                            json_data = {
                                "thought": "Failed to decode LLM response after multiple attempts.",
                                "action": "finish_step",
                                "parameters": {
                                    "result": "LLM response decoding failed",
                                    "status": "failed",
                                    "set_edge_status": {}
                                }
                            }
                            response = json.dumps(json_data)
                            break
                    

            thought = json_data.get("thought", "")
            action = json_data.get("action", "")
            parameters = json_data.get("parameters", {})
            self._record_response(response, prefix=self.step_name)

            # Check for completion - finish_step action
            if action == "finish_step":
                self.console.print(f"[green]Calling `finish_step` detected for step execution[/green]")

                step_result = parameters.get("result", "Step completed")
                step_status = parameters.get("status", "completed")
                set_edge_status = parameters.get("set_edge_status", {})
                self.console.print(f"[green]Parsed finish_step action with {len(set_edge_status)} edge updates[/green]")

                break
            
            self.console.print(f"[blue]Executing action:[/blue] {action} with parameters: {parameters}")
            observation = self._execute_action(action, parameters)
            self._record_observation(observation, prefix=self.step_name)

            # If the action is to call a plugin, run the sql_query_tool directly
            if action.startswith("plugin_"):
                snippet_id = observation.split("SQL query snippet stored with ID: ")[-1].strip()
                self.console.print(f"[blue]Will call SQL plugin directly with snippet ID: {snippet_id}[/blue]")
                # Call the plugin directly with the snippet ID
                sql_action = "sql_query_tool"
                sql_parameters = {
                    "snippet_id": snippet_id,
                    "result_description": f"Result of {self.step_name} step execution"
                }
                self._record_response(
                    json.dumps(
                        {
                            "thought": f"I will execute the SQL query using the plugin with the provided snippet ID: {snippet_id}",
                            "action": sql_action,
                            "parameters": sql_parameters
                        }
                    ),
                    prefix=self.step_name
                )
                self.console.print(f"[blue]Executing SQL action directly:[/blue] {sql_action} with parameters: {sql_parameters}")
                sql_observation = self._execute_action(sql_action, sql_parameters)
                self._record_observation(sql_observation, prefix=self.step_name)

            current_inter += 1

        # If no result was found, generate a default result
        if step_result is None:
            # Fallback if no finish_step action was found
            self.console.print("[yellow]No finish_step action found. Generating default conclusion.[/yellow]")
            
            # Create a fallback result based on the last thought
            step_result = f"Step {self.step_name} was executed, but no finish_step action was provided."
            step_status = "failed"
            set_edge_status = None  # No edge updates in this case

        # Create final structured output
        final_output = {
            "result": step_result,
            "status": step_status,
            "set_edge_status": set_edge_status
        }
        
        # Update execution state with completion info
        self.execution_state.update({
            "status": step_status,
            "end_time": datetime.datetime.now().isoformat(),
            "result": step_result,
            "set_edge_status": set_edge_status
        })
        
        save_agent_trace(
            session_id=self.session_state["session_id"],
            agent_type=self.role,
            agent_id=f"{self.step_name}_{self.agent_id}",  # Use step_name instead of node_id
            data={
                "conversation_history": self.conversation_history,
                "step_info": {
                    "name": self.step_name,
                    "context": context
                },
                "execution_state": self.execution_state,
                "status": self.execution_state["status"],
            }
        )

        return final_output

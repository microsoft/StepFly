import json
import os
from typing import Dict, Any, Optional

from rich.console import Console

from stepfly.agents.base_agent import BaseAgent
from stepfly.utils.memory import Memory
from stepfly.utils.config_loader import config
from stepfly.prompts import Prompts


class Scheduler(BaseAgent):
    """
    Scheduler agent responsible for coordinating the execution of TSG steps based on a PlanDAG.
    This agent follows the REACT pattern (Reasoning, Acting, and Observing) to manage the
    troubleshooting workflow.
    """
    
    def __init__(self, session_id: str, memory: Memory):
        """Initialize the scheduler agent"""
        super().__init__(session_id=session_id, memory=memory)
        self.name = "scheduler"
        self.role = "Scheduler"
        # create a unique session ID for this session

        self.console = Console()
        self.agent_id = memory.register_agent(self.name)

        self._load_tools(session_id=self.session_state["session_id"], memory=self.memory)
        
        # Log to memory
        self.memory.add_data(
            data=self.session_state,
            data_type="scheduler_state",
            agent_id=self.agent_id,
            description=f"Scheduler {self.agent_id} state",
            metadata={"key": f"scheduler_{self.agent_id}_state"}
        )

    
    def start_session(self, incident_id: Optional[str] = None) -> None:
        """Start a new troubleshooting session"""
        session_id = self.session_state["session_id"]
        # Display welcome message
        self.display_message(
            f"Starting new troubleshooting session {session_id}. I will guide you through the process.",
            title="TSG Scheduler"
        )

        system_prompt = Prompts.scheduler_system_structured_prompt()

        # Add tools description to the system prompt
        system_prompt_with_tools = (
            system_prompt + 
            "\n\n\n\n# Available tools:\n" +
            "finish:\n" +
            "## Overview:\n" +
            "This tool is used to complete the troubleshooting session.\n\n" +
            "## Required Parameters:\n" +
            "troubleshooting_conclusion: The conclusion of the troubleshooting session.\n\n" +
            self.tools_description
        )
        
        # Initialize conversation history with system prompt
        self.conversation_history = [
            {"role": "system", "content": system_prompt_with_tools}
        ]

        if not incident_id:
            # Add initial user message
            self.conversation_history.append(
                {"role": "user", "content": "Please start the troubleshooting process by asking me for incident information."}
            )
        else:
            # Add incident ID to the conversation
            self.conversation_history.append(
                {"role": "user", "content": f"Starting troubleshooting for incident ID: {incident_id}"}
            )
        
        # Register conversation
        for message in self.conversation_history:
            self.register_conversation_message(self.agent_id, message)

        # Start REACT loop
        self._react_loop()
    
    def _react_loop(self) -> None:
        """Execute the REACT loop (Reason, Act, Observe)"""
        
        # Get max steps from config
        max_steps = config.get("max_steps", 50)
        single_step_retry_limit = config.get("single_step_retry_limit", 3)
        attempt = 1
        # Execute steps
        for step in range(max_steps):

            while attempt < single_step_retry_limit:
                try:
                    # Get agent's next action
                    response = self.call_llm(self.conversation_history)

                    # Parse response to extract thought, action, and parameters
                    if response.startswith("```json"):
                        response = response[7:]
                    if response.endswith("```"):
                        response = response[:-3]
                    json_data = json.loads(response)

                    thought = json_data.get("thought", "")
                    action = json_data.get("action", "")
                    parameters = json_data.get("parameters", {})

                    # Display the thought (optional)
                    self.display_message(f"Thought: {thought}", title="Reasoning")

                    break  # Exit the retry loop if processing is successful
                except Exception as e:
                    error_message = f"Error processing response: {str(e)}"
                    self.console.print(f"[bold red]{error_message}[/bold red]")
                    # Retry the step
                    attempt += 1
                    continue
            if attempt >= single_step_retry_limit:
                raise RuntimeError(
                    f"Maximum retry limit reached ({single_step_retry_limit}) for step {step + 1}. "
                    "Please check the LLM response format or the conversation history."
                )


            # Record response
            self._record_response(response, prefix="scheduler")

            # Execute the action
            observation = self._execute_action(action, parameters)
            self._record_observation(observation, prefix="scheduler")
            
            # Update session state
            self.session_state["steps_executed"] += 1

            # Check if session is complete
            if action.lower() == "finish":
                self.session_state["complete"] = True
                self.session_state["execution_status"] = "completed"
            
            # Update session state to memory
            self.memory.add_data(
                data=self.session_state,
                data_type="scheduler_state",
                agent_id=self.agent_id,
                description=f"Updated scheduler {self.agent_id} state",
                metadata={"key": f"scheduler_{self.agent_id}_state"}
            )

            if self.session_state["complete"]:
                break

    def _execute_action(self, action: str, parameters: Dict[str, Any]) -> str:
        """
        Execute the specified action with the given parameters
        
        Args:
            action: Name of the action/tool to execute
            parameters: Parameters for the action
            
        Returns:
            Observation from the action
        """
        # Handle empty or invalid action
        if not action or not action.strip():
            return "No action specified. Please provide a valid action to execute."
        
        # Display action
        self.console.print(f"[bold blue]Executing: [/bold blue][bold green]{action}[/bold green]")
        
        # Normalize action name (remove spaces, lowercase)
        normalized_action = action.lower().replace(" ", "_").strip()
        
        # Handle special finish action
        if normalized_action in ["finish", "complete", "done"]:
            # Check if troubleshooting_conclusion is provided
            conclusion = parameters.get("troubleshooting_conclusion", "")
            if conclusion:
                # Format the conclusion for display (handle both string and dict formats)
                if isinstance(conclusion, dict):
                    # Convert dictionary to formatted string
                    formatted_conclusion = self._format_conclusion_dict(conclusion)
                elif isinstance(conclusion, str):
                    formatted_conclusion = conclusion
                else:
                    # Convert other types to string
                    formatted_conclusion = str(conclusion)
                
                # Display the troubleshooting conclusion
                # self.display_message(
                #     formatted_conclusion,
                #     title="🔍 Troubleshooting Conclusion",
                #     style="bold green"
                # )
                
                # Store the conclusion in session state (keep original format)
                self.session_state["troubleshooting_conclusion"] = conclusion
                
                return f"Session completed successfully with conclusion: {formatted_conclusion}"
            else:
                return "Session completed successfully."
        
        # Look for matching tool
        for tool_name, tool in self.tools.items():
            # Require exact match or the normalized action should be a meaningful substring
            if (normalized_action == tool_name or 
                (len(normalized_action) > 2 and normalized_action in tool_name)):
                try:
                    # Execute the tool with parameters
                    result = tool.execute(**parameters)
                    
                    # Store TSG name if loading TSG
                    if tool_name == "tsg_loader" and "path" in parameters:
                        tsg_path = parameters.get("path")
                        tsg_filename = os.path.basename(tsg_path).split('.')[0]
                        # Remove common suffixes
                        for suffix in ["_WITH_REFERENCES", "_WITH_PLUGIN_REFERENCES"]:
                            if tsg_filename.endswith(suffix):
                                tsg_filename = tsg_filename[:-len(suffix)]
                                break
                        self.session_state["current_tsg_name"] = tsg_filename
                    
                    return result
                except Exception as e:
                    error_message = f"Error executing {tool_name}: {str(e)}"
                    self.console.print(f"[bold red]{error_message}[/bold red]")
                    return error_message
        
        # No matching tool found
        available_tools = ", ".join(self.tools.keys())
        return f"Unknown action: '{action}'. Available tools: {available_tools}"

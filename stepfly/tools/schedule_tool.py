import json
import multiprocessing
multiprocessing.set_start_method('spawn', force=True)
import threading
import time
import uuid
from datetime import datetime
from typing import Dict, Any, List, Tuple

from rich.console import Console
from rich.table import Table

from stepfly.agents.executor import Executor
from stepfly.utils.memory import Memory
from stepfly.tools.base_tool import BaseTool
from stepfly.utils.config_loader import config


def _set_all_output_edges_disabled(node: Dict[str, Any], edge_status: List[Dict[str, Any]]) -> None:
    output_edges = node.get("output_edges", [])
    output_edge_names = set([node_info.get("edge") for node_info in output_edges])

    # Disable all output edges
    for edge in edge_status:
        if edge["edge"] in output_edge_names:
            # Update status to disabled
            edge["status"] = "disabled"


def _are_all_input_edges_disabled(node: Dict[str, Any], edge_status: List[Dict[str, Any]]) -> bool:
    input_edges = node.get("input_edges", [])

    # If no input edges, return False
    if not input_edges:
        raise ValueError(f"Node {node['node']} has no input edges defined, cannot check for disabled status.")

    input_edge_names = set([node_info.get("edge") for node_info in input_edges])

    for edge in edge_status:
        if edge["edge"] in input_edge_names:
            # If any input edge is not disabled, return False
            if edge["status"] != "disabled":
                return False

    # All edges are disabled
    return True


def _should_trigger_node(node: Dict[str, Any], edge_status: List[Dict[str, Any]]) -> Tuple[bool, bool]:
    node_name = node["node"]
    input_edges = node.get("input_edges", [])

    if not input_edges:
        # start node should not be checked here, it should be handled separately
        raise ValueError(f"Node {node_name} has no input edges defined, cannot check for triggering status.")

    input_edge_names = set([node_info.get("edge") for node_info in input_edges])
    input_edge_status = {}
    any_enabled = False    # At least one edge is enabled
    any_pending = False
    is_end_node = node_name.lower() in ["end"]

    for edge in edge_status:
        if edge["edge"] in input_edge_names:
            # If any input edge is pending, we cannot trigger the node
            if edge["status"] == "pending":
                any_pending = True
            # If any input edge is enabled, we can trigger the node
            if edge["status"] == "enabled":
                any_enabled = True
            # Store the status for debug output
            input_edge_status[edge["edge"]] = edge["status"]

    edge_status_str = ', '.join([f"{k}: {v}" for k, v in input_edge_status.items()])
    if is_end_node and any_enabled:
        print(f"End node {node_name} can be triggered if any input edge is enabled. {edge_status_str}")
        return True, True

    if not any_pending and any_enabled:
        # print(f"Node {node_name} can be triggered: all input edges are determined and at least one is enabled. {edge_status_str}")
        return True, False

    return False, False


def _update_output_edges(all_edge_status, set_edge_status):
    for edge_name, new_status in set_edge_status.items():
        edge_found = False
        for edge in all_edge_status:
            if edge["edge"] == edge_name:
                old_status = edge["status"]
                edge["status"] = new_status
                edge_found = True
                print(f"[green]✓ Updated {edge_name}: {old_status} -> {new_status}[/green]")
                break

        if not edge_found:
            print(f"[red]✗ Edge '{edge_name}' not found, should revise the DAG[/red>")
            raise ValueError(f"Edge '{edge_name}' not found in Edge_Status")


def _run_executor(
        node: Dict[str, Any],
        executor_agent_id: str,
        session_id: str,
        node_context: str,
        max_retry_number: int = 3,
) -> None:
    node_name = node["node"]
    print(f"[blue]Starting executor {executor_agent_id} for node: {node_name}[/blue]")

    memory = Memory(session_id=session_id)
    # Create executor instance
    executor = Executor(
        step_name=node_name,
        session_id=session_id,
        memory=memory,
        agent_id=executor_agent_id
    )

    # Execute the step
    print(f"[blue]Executor {executor_agent_id} executing node: {node_name}[/blue]")
    step_result = executor.execute_step(node_context, max_retry_number=max_retry_number)

    # Update step result in memory
    print(f"[blue]Executor {executor_agent_id} finished node: {node_name} with result: {step_result}[/blue]")
    memory.add_data(
        data={
            "node_name": node_name,
            "executor_id": executor_agent_id,
            "result": step_result
        },
        data_type="executor_result",
        agent_id=executor_agent_id,
        description=f"Store execution result for node {node_name}",
        metadata={"key": f"{executor_agent_id}_step_result"}
    )


def _is_execution_complete(all_node_status: Dict[str, Any], all_edge_status: Dict[str, Any]) -> bool:
    # Check if end node is finished
    end_node = next((node for node in all_node_status if node["node"].lower() in ["end"]), None)
    if end_node and end_node["status"] == "finished":
        print("[green]Execution complete: End node is finished.[/green]")
        return True

    # Check if any edges are still pending
    any_pending_edges = any(edge["status"] == "pending" for edge in all_edge_status)

    # Check if any nodes are still running
    any_unfinished_nodes = any(node["status"] in ["pending", "running"] for node in all_node_status)

    # Execution is complete if no edges are pending and no nodes are running
    return not any_pending_edges and not any_unfinished_nodes


def format_assistant_message(message: str) -> str:
    message_obj = json.loads(message)
    action = message_obj.get("action", "")
    parameters = message_obj.get("parameters", "{}")
    return f"Action: tool `{action}` is called with parameters: {parameters}"


class ScheduleTool(BaseTool):
    """Tool for monitoring edge status and deploying executors asynchronously"""
    
    def __init__(self, session_id: str, memory: Memory):
        super().__init__(session_id, memory)
        self.tsg_path = None
        self.incident_id = None
        self.name="schedule_tool"
        self.description=(
            "Monitor edge status and deploy executors for workflow nodes based on PlanDAG structure.\n\n"
            "Required Parameters:\n"
            "- incident_id: The incident ID for context\n"
            "- tsg_path: Path to the TSG document"
        )
        self.console = Console()
        self.running_nodes = {}  # Set to track currently running nodes
        self.monitoring_thread = None
        self.running = False
        
    def execute(self, incident_id: str, tsg_path: str) -> str:
        """
        Start monitoring edge status and deploying executors
        
        Args:
            incident_id: The incident ID for context
            tsg_path: Path to the TSG document
            
        Returns:
            Final summary of the execution
        """
        try:
            # Store parameters for use in monitoring thread
            self.incident_id = incident_id
            self.tsg_path = tsg_path
            
            # Start monitoring thread
            self.running = True
            self.monitoring_thread = threading.Thread(target=self._monitoring_loop)
            self.monitoring_thread.daemon = True
            self.monitoring_thread.start()
            
            # Display initial status
            self._display_status_table()
            
            # Wait for execution to complete - use a timeout to allow checking for manual interruption
            while self.running:
                # Wait for a short period
                time.sleep(30)
                
                # Display updated status
                self._display_status_table()

                if not self.running:
                    break
            
            # Wait for monitoring thread to complete
            if self.monitoring_thread and self.monitoring_thread.is_alive():
                self.monitoring_thread.join(timeout=10)
            
            # Generate final summary
            summary = self._generate_summary()
            
            return summary
            
        except Exception as e:
            self.running = False
            return f"Error in schedule_tool: {str(e)}"
    
    def _monitoring_loop(self) -> None:
        """Monitor edge status and trigger nodes based on input edge conditions"""
        check_interval = 1  # Check frequency in seconds
        executor_timeout = 180  # Timeout for executor processes in seconds
        max_executor_number = config.get("scheduler.max_executor_number", 3)  # Maximum number of concurrent executors, default 3

        print("------>", datetime.now(), "Starting monitoring loop for edge status and node execution...")

        while self.running:
            # Get latest edge status - ALWAYS fetch fresh from memory
            all_edge_status = self.memory.get_data_by_key("Edge_Status")

            # Get latest node status - ALWAYS fetch fresh from memory
            all_node_status = self.memory.get_data_by_key("Node_Status")

            # Get executor results
            nodes_to_pop = []
            for executor_id in self.running_nodes:
                # check is_alive for each executor
                process_status = self.running_nodes[executor_id]["process"].is_alive()
                is_timeout = False
                if not process_status:
                    self.running_nodes[executor_id]["process"].join(timeout=1)
                else:
                    process_start_time = self.running_nodes[executor_id]["start_time"]
                    if (datetime.now() - process_start_time).total_seconds() > executor_timeout:
                        self.console.print(f"[red]Executor {executor_id} timed out, terminating it.[/red]")
                        self.running_nodes[executor_id]["process"].terminate()
                        self.running_nodes[executor_id]["process"].join(timeout=1)
                        is_timeout = True

                if is_timeout:
                    executor_result = {
                        "node_name": self.running_nodes[executor_id]["node_name"],
                        "executor_id": executor_id,
                        "result": {
                            "status": "failed",
                            "error": "Executor timed out"
                        }
                    }
                    # save a flag file to track timeout
                    with open(f"trace/{self.session_id}/{executor_id}_timeout.flag", "w") as f:
                        f.write("timeout")
                else:
                    executor_result = self.memory.get_data_by_key(f"{executor_id}_step_result")

                if not executor_result:
                    continue

                # Process the result and update node status
                node_name = executor_result["node_name"]
                node_status = "finished" if executor_result["result"]["status"] == "completed" else "failed"
                set_edge_status = executor_result["result"].get("set_edge_status", {})
                self.console.print(f"[cyan]Processing result for node: {node_name} - Status: {node_status}[/cyan]")

                for node in all_node_status:
                    if node["node"] == node_name:
                        # Update node status based on executor result
                        node["status"] = node_status
                        node["result"] = json.dumps(executor_result["result"])  # Store result as JSON string

                        if node_status == "finished":
                            # Update edge status based on set_edge_status
                            print(f"[green]Node {node_name} finished, updating output edges {set_edge_status}[/green]")
                            _update_output_edges(all_edge_status, set_edge_status)
                        else:
                            # If node is not finished, disable all output edges
                            print(f"[yellow]Node {node_name} failed, disabling all output edges[/yellow]")
                            _set_all_output_edges_disabled(node, all_edge_status)

                nodes_to_pop.append(executor_id)  # Mark this executor for removal
                start_time = self.running_nodes[executor_id]["start_time"]
                print(f"[blue]Executor {executor_id} {node_status} for node {node_name} at {datetime.now()}, started at {start_time}[/blue]")

            for executor_id in nodes_to_pop:
                # Remove completed executors from tracking
                if executor_id in self.running_nodes:
                    del self.running_nodes[executor_id]
                    self.console.print(f"[green]Removed completed executor: {executor_id}[/green]")

            nodes_to_run = []
            is_end_triggered = False
            # Monitor edge status and trigger nodes
            for node in all_node_status:
                node_name = node["node"]

                # Skip nodes that are not pending or already deployed
                if node["status"] != "pending":
                    continue

                # Check if all input edges are in ["enabled", "disabled"] and at least one is "enabled"
                is_triggering, is_end_node = _should_trigger_node(node, all_edge_status)
                if is_triggering and (is_end_node or len(self.running_nodes) + len(nodes_to_run) < max_executor_number):
                    self.console.print(f"[green]Triggering node: {node_name} ({len(self.running_nodes)}:{len(nodes_to_run)})[/green]")
                    nodes_to_run.append(node)
                    if is_end_node:
                        is_end_triggered = True

                # Check if all input edges are disabled - if so, set all output edges disabled
                elif _are_all_input_edges_disabled(node, all_edge_status):
                    self.console.print(f"[yellow]All input edges disabled for node: {node_name}, disabling output edges[/yellow]")

                    # Set node status to skipped using fresh node_status
                    node["status"] = "skipped"

                    # Disable all output edges using fresh edge_status
                    _set_all_output_edges_disabled(node, all_edge_status)
            
            for node in nodes_to_run:
                if is_end_triggered and node["node"].lower() not in ["end"]:
                    continue    # If end node is triggered, do not start any other nodes except end node
                
                # Update status to running and assign executor ID
                node_name = node["node"]
                node["status"] = "running"
                node["executor_id"] = str(uuid.uuid4())  # Assign a new executor ID for this node
                self.console.print(f"[blue]Assigned executor ID {node['executor_id']} to node: {node_name}[/blue]")
                # Deploy executor asynchronously with snapshot of current edge and node status\
                # Start executor in a separate thread
                executor_process = multiprocessing.Process(
                    target=_run_executor,
                    args=(
                        node,
                        node["executor_id"],
                        self.session_id,
                        self._build_executor_context(node, all_node_status),
                        3,  # Max retry number for executor
                    )
                )
                executor_process.daemon = True
                self.console.print(f"[blue]Starting executor process for node: {node_name} with executor ID: {node['executor_id']}[/blue]")
                executor_process.start()

                self.running_nodes[node["executor_id"]] = {
                    "start_time": datetime.now(),
                    "node_name": node_name,
                    "process": executor_process
                }
            

            # Update node status and edge status in memory
            self.memory.update_data_by_key(
                key="Node_Status",
                data=all_node_status,
                data_type="node_status",
                description="Updated node status after monitoring loop"
            )

            self.memory.update_data_by_key(
                key="Edge_Status",
                data=all_edge_status,
                data_type="edge_status",
                description="Updated edge status after monitoring loop"
            )

            # Check if execution is complete with fresh data
            if _is_execution_complete(all_node_status, all_edge_status):
                self.running = False
                break

            # Sleep before next check
            time.sleep(check_interval)

        print("------>", datetime.now(), "Monitoring loop ended.")
        # clean up running executors
        for executor_id in self.running_nodes:
            # check is_alive for each executor
            process_status = self.running_nodes[executor_id]["process"].is_alive()

            if not process_status:
                self.running_nodes[executor_id]["process"].join(timeout=1)
            else:
                self.console.print(f"[red]Executor {executor_id} is running after completion, terminating it.[/red]")
                self.running_nodes[executor_id]["process"].terminate()
                self.running_nodes[executor_id]["process"].join(timeout=1)


    def _build_executor_context(self, node: Dict[str, Any], node_status: List[Dict[str, Any]]) -> str:
        # todo: replace with the actual node name
        node_real_name = node.get("node")
        context = f"# Context for {node_real_name} execution\n\n"

        # Add incident information
        incident_info = self.memory.get_data_by_key("incident_info")
        if incident_info:
            context += "## Incident Information\n"
            context += f"{incident_info}\n\n"
            context += "<!-- INCIDENT INFO END -->\n\n"

        # Add TSG content
        tsg_content = self.memory.get_data_by_key("tsg_content")
        if tsg_content:
            context += "## TSG Document\n"
            context += f"{tsg_content}\n\n"
            context += "<!-- TSG DOCUMENT END -->\n\n"

        # Add predecessor/completed node information based on configuration
        node_context_info = self._get_node_context_info(node, node_status)
        if node_context_info:
            context += "## Previous Steps that have been completed\n"
            context += node_context_info
            context += "<!-- PREVIOUS STEPS END -->\n\n"

        # Add role description
        context += f"# Now, begin your execution for {node_real_name}!\n\n"
        context += (f"You are responsible for executing a single step, i.e., {node_real_name}, in the TSG document. "
                    "Your job is to complete the assigned step and provide a structured conclusion with edge status updates. "
                    "Do **not** execute any step, sub-step, or content that is not part of the assigned step. "
                    "A step may have sub-steps. Unless you are explicitly instructed to execute a sub-step, do not execute it. "
                    f"If {node_real_name} has sub-steps, but the step itself (i.e., before the first sub-step) is only a overview "
                    f"and does not have any meaningful execution content such as KQL, geneva, deployment, pull requests, etc., "
                    "just call `finish_step` with a summary to skip it. For tasks that does not require tool execution but only reasoning, "
                    "use `log_reasoning_tool` instead to log your reasoning process."
                    "\n\n")

        # Add output requirements
        output_edges = node.get("output_edges", [])
        if output_edges:
            context += "## Output Requirements\n\n"
            context += "When your execution is complete, you MUST call `finish_step` action as follows:\n\n"
            context += "```json\n"
            context += "{\n"
            context += '  "thought": "Your analysis and conclusion.",\n'
            context += '  "action": "finish_step",\n'
            context += '  "parameters": {\n'
            context += '    "result": "Detailed summary of your findings and conclusions",\n'
            context += '    "set_edge_status": {\n'

            for i, edge_info in enumerate(output_edges):
                edge_name = edge_info.get("edge", f"edge_{i}")
                condition = edge_info.get("condition", "none")
                comma = "," if i < len(output_edges) - 1 else ""
                if condition and condition != "none":
                    context += f'      "{edge_name}": "enabled/disabled"  // Based on: {condition}{comma}\n'
                else:
                    context += f'      "{edge_name}": "enabled/disabled"{comma}\n'

            context += "    }\n"
            context += "  }\n"
            context += "}\n"
            context += "```\n\n"

            context += "The available output edges and their conditions are:\n"
            for edge_info in output_edges:
                edge_name = edge_info.get("edge", "unknown")
                condition = edge_info.get("condition", "none")
                if condition and condition != "none":
                    context += f"- {edge_name}: Enable if {condition}\n"
                else:
                    context += f"- {edge_name}: Unconditional connection\n"
        else:
            context += "## Output Requirements\n\n"
            context += ("No output edges defined for this step, which is the end of the workflow.\n"
                        "You can still provide a result summary calling `finish_step`, but no edge status updates will be required.\n\n")
            context += "You can simply finish the step with the format:\n\n"
            context += "```json\n"
            context += "{\n"
            context += '  "thought": "Your analysis and conclusion.",\n'
            context += '  "action": "finish_step",\n'
            context += '  "parameters": {}\n'
            context += '}\n'
            context += "```\n\n"

        return context

    def _get_node_context_info(self, node: Dict[str, Any], node_status: List[Dict[str, Any]], include_conversation: bool = True) -> str:
        # Determine which nodes to include in context
        target_nodes = set()

        current_step_number = node["node"]

        # Assumption: the TSG steps are ordered by their step numbers and the order is aligned with the plan DAG nodes
        last_node_name = None
        for status_node in node_status:
            if status_node["node"] == current_step_number:
                break
            if status_node["status"] != "finished":
                continue
            target_nodes.add(status_node["node"])
            last_node_name = status_node["node"]
        print("[DEBUG] Adding ordered step context:", [node for node in target_nodes], "to current step:", current_step_number)
        
        # Collect information from target nodes, ordered by their position in node_status
        results = []
        for node_info in node_status:
            # Only process nodes that are in target_nodes and have finished status
            if node_info["node"] not in target_nodes:
                continue

            # Include full node context
            context_parts = [f"### {node_info['node']} Context", f"**Status**: {node_info['status']}",
                             f"**Description**: {node_info.get('description', 'N/A')}"]

            if node_info.get("result"):
                node_result = json.loads(node_info["result"])
                context_parts.append(f"**Result**: {node_result['result']}")
                edge_updates = "; ".join([f"{edge}->{status}" for edge, status in node_result.get("set_edge_status", {}).items()])
                context_parts.append(f"**Edge Status Updates**: {edge_updates if edge_updates else 'None'}")

            # Add conversation history if executor_id is available
            if include_conversation:
                executor_id = node_info.get("executor_id")
                if executor_id:
                    conversation_history = self.memory.get_agent_context(executor_id, message_only=True)
                    if conversation_history:
                        context_parts.append("**Conversation History**:")
                        # Process each message with appropriate handling, skip first system and user messages to avoid duplication
                        conversation_history_length = len(conversation_history)
                        for i, msg in enumerate(conversation_history):
                            # Skip the first system message and first user message to avoid duplication
                            if i < 2:
                                continue
                            role = msg.get("role", "")
                            content = msg.get("content", "")

                            if role == "assistant":
                                context_parts.append(f"- " + format_assistant_message(content))
                            elif role == "user":
                                context_parts.append(f"- {content}")


            results.append("\n".join(context_parts) + "\n")
        
        return "\n".join(results) if results else ""

    def _display_status_table(self) -> None:
        """Display a table with the current status of all nodes and edges"""
        node_status = self.memory.get_data_by_key("Node_Status")
        edge_status = self.memory.get_data_by_key("Edge_Status")
        
        if not node_status or not edge_status:
            return
        
        # Node status table
        node_table = Table(title="Node Execution Status")
        node_table.add_column("Node", style="cyan")
        node_table.add_column("Status", style="magenta")
        
        for node in node_status:
            node_name = node["node"]
            status = node["status"]
            status_display = status.upper()
            
            # Add color based on status
            if status == "finished":
                status_display = f"[green]{status_display}[/green]"
            elif status == "running":
                status_display = f"[yellow]{status_display}[/yellow]"
            elif status == "failed":
                status_display = f"[red]{status_display}[/red]"
            elif status == "skipped":
                status_display = f"[blue]{status_display}[/blue]"
            
            node_table.add_row(node_name, status_display)
        
        # Edge status table
        edge_table = Table(title="Edge Status")
        edge_table.add_column("Edge", style="cyan")
        edge_table.add_column("Status", style="magenta")
        
        for edge in edge_status:
            edge_id = edge["edge"]
            status = edge["status"]
            status_display = status.upper()
            
            # Add color based on status
            if status == "enabled":
                status_display = f"[green]{status_display}[/green]"
            elif status == "disabled":
                status_display = f"[red]{status_display}[/red]"
            elif status == "pending":
                status_display = f"[yellow]{status_display}[/yellow]"
            
            edge_table.add_row(edge_id, status_display)
        
        # Display tables
        self.console.print(node_table)
        self.console.print(edge_table)
    
    def _generate_summary(self) -> str:
        """
        Generate a summary of the execution results
        
        Returns:
            Summary text
        """
        node_status = self.memory.get_data_by_key("Node_Status")
        if not node_status:
            return "No execution data found."
        
        # Collect all step results
        results = []
        for node in node_status:
            if node["status"] == "finished" and node.get("result"):
                results.append({
                    "step": node["node"],
                    "result": node["result"]
                })
        
        # Build summary text
        summary = "# Troubleshooting Execution Summary\n\n"
        
        # Add execution statistics
        total_nodes = len(node_status)
        finished_nodes = sum(1 for node in node_status if node["status"] == "finished")
        failed_nodes = sum(1 for node in node_status if node["status"] == "failed")
        skipped_nodes = sum(1 for node in node_status if node["status"] == "skipped")
        
        summary += f"Execution completed with {finished_nodes}/{total_nodes} steps finished successfully.\n"
        if failed_nodes > 0:
            summary += f"{failed_nodes} steps failed.\n"
        if skipped_nodes > 0:
            summary += f"{skipped_nodes} steps skipped.\n"
        
        # Add end node result if available
        end_node = next((node for node in node_status if node["node"].lower() in ["end"]), None)
        if end_node and end_node["status"] == "finished" and end_node.get("result"):
            summary += "\n## Final Conclusion\n"
            summary += end_node["result"]
        
        return summary 
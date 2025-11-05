import os
import json
import re
import importlib
from typing import Dict, Any, List

from stepfly.utils.memory import Memory
from stepfly.utils.config_loader import config
from stepfly.tools.base_tool import BaseTool
from stepfly.utils.file_utils import FileUtils


class IncidentTSGLoader(BaseTool):
    """Tool for loading incident information, corresponding TSG document, and PlanDAG in one operation"""
    
    def __init__(self, session_id: str, memory: Memory):
        super().__init__(session_id, memory)
        self.name = "incident_tsg_loader"
        self.description = (
            "Load incident information, the corresponding TSG document, and its PlanDAG.\n\n"
            "Required Parameters:\n"
            "- incident_id: The incident ID number (e.g., \"642017861\")"
        )
        
        # Load configuration for incident_info functionality
        sql_config = config.get_section("database.sql")
        self.connection = sql_config.get("connection", "sqlite:///demo_incidents.db")
        self.database = sql_config.get("database", "incidents_db")
        self.driver = sql_config.get("driver", "sqlite")
        
        # Initialize file utils for tsg_loader functionality
        self.file_utils = FileUtils()
        
        # Load TSG and PlanDAG base paths from config
        tsg_config = config.get_section("tools.tsg_loader")
        self.tsg_base_path = tsg_config.get("tsg_base_path", "./TSGs")
        self.plandag_base_path = tsg_config.get("plandag_base_path", "./TSGs/PlanDAGs")
        
        # Load incident to TSG mapping
        self.incident_tsg_map = self._load_incident_tsg_map()
    
    def execute(self, incident_id: str) -> str:
        """
        Load incident information, corresponding TSG document, and PlanDAG
        
        Args:
            incident_id: The incident ID to query
            
        Returns:
            Combined incident information, TSG content, and PlanDAG status
        """
        try:
            # Step 1: Load incident information (using exact incident_info logic)
            incident_result = self._load_incident_info(incident_id)
            
            # Step 2: Map incident ID to TSG document
            tsg_filename = self.incident_tsg_map.get(incident_id)
            if not tsg_filename:
                return f"{incident_result}\n\nNo TSG mapping found for incident ID {incident_id}. Please manually select and load a TSG document."
            
            # Step 2.5: Check if plugins are disabled and modify TSG filename accordingly
            enable_plugins = config.get("tools.enable_plugins", True)
            if not enable_plugins and tsg_filename.endswith("_WITH_REFERENCES.md"):
                # Remove _WITH_REFERENCES suffix to use original TSG without plugins
                tsg_filename = tsg_filename.replace("_WITH_REFERENCES.md", ".md")
            
            # Step 3: Load TSG document (using exact tsg_loader logic)
            tsg_result = self._load_tsg_document(tsg_filename)
            
            # Step 4: Load corresponding PlanDAG
            plandag_result = self._load_plandag(tsg_filename)
            
            # Step 5: Return combined results
            combined_result = f"{incident_result}\n\n{'='*60}\n\nTSG Document Loaded: {tsg_filename}\n\n{tsg_result}"
            if plandag_result:
                combined_result += f"\n\n{'='*60}\n\n{plandag_result}"
            
            return combined_result
            
        except Exception as e:
            return f"Error in incident TSG loading: {str(e)}"
    
    def _load_incident_info(self, incident_id: str) -> str:
        """
        Load incident information from files in incidents directory
        """
        try:
            # Try to find the incident file
            incident_path = None
            possible_paths = [
                f"incidents/{incident_id}.txt",
                f"incidents/{incident_id}",
                incident_id  # Direct path
            ]
            
            for path in possible_paths:
                if os.path.exists(path):
                    incident_path = path
                    break
            
            if not incident_path:
                return f"Error: Could not find incident file for ID '{incident_id}'"
            
            # Read the incident content
            with open(incident_path, 'r', encoding="utf-8") as f:
                incident_content = f.read()
            
            # Store incident_id in memory for other tools to use
            self.memory.add_data(
                data=incident_id,
                data_type="incident_metadata",
                metadata={"key": "incident_id"},
                description=f"Incident ID for current troubleshooting session"
            )
            
            # Remove URLs to avoid unintended actions
            url_pattern = r"https?://\S+|www\.\S+"
            formatted_content = re.sub(url_pattern, "[URL removed]", incident_content)
            
            # Store incident info in memory for other tools to access
            self.memory.add_data(
                data=formatted_content,
                data_type="incident_info",
                description=f"Incident information for ID {incident_id}",
                metadata={"key": "incident_info", "incident_id": incident_id}
            )
            
            return f"Incident Information for ID {incident_id} (from file):\n\n{formatted_content}"

        except Exception as e:
            return f"Error retrieving incident information: {str(e)}"
    
    def _load_tsg_document(self, tsg_filename: str) -> str:
        """
        Load TSG document using the exact logic from tsg_loader tool
        """
        try:
            # Use configured TSG base path
            path = os.path.join(self.tsg_base_path, tsg_filename)
            if not os.path.exists(path):
                return f"Error: TSG file not found at {path}"
            
            content = self.file_utils.read_file(path)
            
            # Extract TSG name (removing any _WITH_REFERENCES suffix)
            tsg_name = self._get_base_tsg_name(os.path.basename(path))
            
            # Process code block references
            processed_content = self._process_code_block_references(content)
            
            # Add plugin information directly without loading classes (only if plugins are enabled)
            enable_plugins = config.get("tools.enable_plugins", True)
            if enable_plugins:
                plugin_info = self._get_plugin_info_as_text(tsg_name)
                if plugin_info:
                    processed_content += "\n\n" + plugin_info
                    
                    # Add special marker for executor to detect plugins
                    processed_content += f"\n\n<!-- TSG_PLUGINS:{tsg_name} -->"
            
            # Store TSG content in memory for other tools to access
            self.memory.add_data(
                data=processed_content,
                data_type="tsg_content",
                description=f"TSG document content for {tsg_name}",
                metadata={"key": "tsg_content", "tsg_name": tsg_name, "path": path}
            )
            
            return processed_content
            
        except Exception as e:
            return f"Error reading TSG file: {str(e)}"
    
    def _load_incident_tsg_map(self) -> Dict[str, str]:
        """
        Load the incident to TSG mapping from config file
        """
        try:
            map_file = "config/incident_tsg_map.json"
            if os.path.exists(map_file):
                with open(map_file, 'r') as f:
                    return json.load(f)
            return {}
        except Exception as e:
            print(f"Warning: Could not load incident TSG map: {str(e)}")
            return {}
    
    def _process_code_block_references(self, content: str) -> str:
        """
        Replace code block sections with shortened references or keep full content based on config
        """
        # Check configuration to determine if we should show full plugin content
        show_full_content = config.get("tools.tsg_loader.show_full_plugin_content", False)
        
        if show_full_content:
            # Keep original content but add execution instruction before closing tag
            pattern = re.compile(r'(\S*)<PLUGIN_(\d+)>(.*?)(\S*)</PLUGIN_\2>', re.DOTALL)
            return pattern.sub(
                lambda m: f"{m.group(1)}<PLUGIN_{m.group(2)}>{m.group(3)}\n\nPlease directly execute tool plugin_{m.group(2)} {m.group(4)}</PLUGIN_{m.group(2)}> if you need to execute the code",
                content
            )
        else:
            # Original behavior: replace with shortened references
            pattern = re.compile(r'(\S*)<PLUGIN_(\d+)>.*?(\S*)</PLUGIN_\2>', re.DOTALL)
            return pattern.sub(lambda m: f"{m.group(1)}<please execute query plugin_{m.group(2)}>{m.group(3)}", content)
    
    def _get_plugin_info_as_text(self, tsg_name: str) -> str:
        """
        Get information about plugins by loading them and using their built-in methods
        
        Args:
            tsg_name: Name of the TSG
            
        Returns:
            Text description of available plugins in markdown format
        """
        plugins_dir = os.path.join("./plugins", tsg_name)
        if not os.path.exists(plugins_dir):
            return ""
        
        plugin_files = [f for f in os.listdir(plugins_dir) 
                       if f.endswith('.py') and f != '__init__.py']
        
        def natural_sort_key(s):
            return [int(text) if text.isdigit() else text.lower() 
                    for text in re.split(r'(\d+)', s)]
        plugin_files.sort(key=natural_sort_key)

        if not plugin_files:
            return ""
        
        result = "## SQL Query Preparation plugins in this TSG:\n\n"
        
        # Import the module that contains BasePlugin
        from plugins.base_plugin import BasePlugin

        for plugin_file in plugin_files:
            plugin_id = plugin_file[:-3]  # Remove .py extension

            # Dynamically import the plugin module
            module_name = f"plugins.{tsg_name}.{plugin_id}"
            plugin_module = importlib.import_module(module_name)

            # Find the plugin class (should be the only class that inherits from BasePlugin)
            plugin_class = None
            for attr_name in dir(plugin_module):
                attr = getattr(plugin_module, attr_name)
                if isinstance(attr, type) and issubclass(attr, BasePlugin) and attr is not BasePlugin:
                    plugin_class = attr
                    break

            if plugin_class:
                # Instantiate the plugin
                plugin_instance = plugin_class()

                # Get plugin information using its built-in methods
                plugin_info = plugin_instance.get_description()

                # Format the information
                name = plugin_info.get("name", plugin_id)
                description = plugin_info.get("description", "No description available")
                language = plugin_info.get("language", "")

                # Build the markdown output
                lang_text = f" ({language})" if language else ""
                result += f"### {name}{lang_text}\n\n"
                result += f"{description}\n"

                # Add parameters information if available
                if hasattr(plugin_instance, "parameters") and plugin_instance.parameters:
                    result += "\n**Parameters**:\n"
                    for param in plugin_instance.parameters:
                        param_name = param.get("name", "")
                        param_desc = param.get("description", "")
                        if param_name and param_desc:
                            result += f"  - `{param_name}`: {param_desc}\n"

                result += f"\n**Usage**: Use `{plugin_id}_tool` directly\n\n"
            else:
                raise RuntimeError(f"Plugin class not found in {module_name}")

        return result
    
    def _get_base_tsg_name(self, filename: str) -> str:
        """
        Get base TSG name by removing any suffixes like _WITH_REFERENCES
        
        Args:
            filename: TSG filename (with or without extension)
            
        Returns:
            Base TSG name without suffixes
        """
        # Remove file extension
        name = filename.split('.')[0]
        
        # Remove common suffixes
        for suffix in ["_WITH_REFERENCES", "_WITH_PLUGIN_REFERENCES"]:
            if name.endswith(suffix):
                name = name[:-len(suffix)]
                break
        
        return name
    
    def _load_plandag(self, tsg_filename: str) -> str:
        """
        Load PlanDAG file and initialize Edge_Status and Node_Status tables
        """
        try:
            # Get base TSG name
            tsg_name = tsg_filename.replace(".md", "")
            
            # Construct PlanDAG path using configured base path
            plan_dag_path = os.path.join(self.plandag_base_path, f"{tsg_name}_plan_dag.json")
            
            if not os.path.exists(plan_dag_path):
                return f"Warning: PlanDAG file not found at {plan_dag_path}. Continuing without PlanDAG."
            
            # Load the PlanDAG
            with open(plan_dag_path, 'r', encoding='utf-8') as f:
                plan_dag_data = json.load(f)
            
            plan_dag_nodes = plan_dag_data.get("nodes", [])
            if not isinstance(plan_dag_nodes, list):
                return f"Error: Invalid PlanDAG format. Expected a list of nodes."
            
            # Extract all edges from nodes and create Edge_Status table
            edge_status = []
            all_edges = set()
            
            # Collect all unique edges from all nodes
            for node in plan_dag_nodes:
                # Process output edges
                for edge_info in node.get("output_edges", []):
                    edge_name = edge_info.get("edge")
                    if edge_name and edge_name not in all_edges:
                        all_edges.add(edge_name)
                        edge_status.append({
                            "edge": edge_name,
                            "status": "pending",
                            "condition": edge_info.get("condition", "none")
                        })
                
                # Also process input edges to ensure we get all edges
                for edge_info in node.get("input_edges", []):
                    edge_name = edge_info.get("edge")
                    if edge_name and edge_name not in all_edges:
                        all_edges.add(edge_name)
                        edge_status.append({
                            "edge": edge_name,
                            "status": "pending",
                            "condition": edge_info.get("condition", "none")
                        })
            
            # Find start node and enable its output edges
            start_node = next((node for node in plan_dag_nodes if node.get("node", "").lower() == "start"), None)
            if not start_node:
                raise ValueError("No start node found in the PlanDAG. Please ensure a start node is defined.")

            # Set start node as finished
            start_node["status"] = "finished"
            # Enable all output edges from start node
            for edge_info in start_node.get("output_edges", []):
                edge_name = edge_info.get("edge")
                if edge_name:
                    for edge in edge_status:
                        if edge["edge"] == edge_name:
                            edge["status"] = "enabled"
                            break
            
            # Store edge status in memory with specific key
            self.memory.add_data(
                data=edge_status,
                data_type="edge_status",
                description="Current status of all edges in the PlanDAG",
                metadata={"key": "Edge_Status"}
            )
            
            # Create Node_Status from Plan_DAG with additional fields
            node_status = []
            for node in plan_dag_nodes:
                node_status.append({
                    "node": node["node"],
                    "description": node.get("description", ""),
                    "input_edges": node.get("input_edges", []),
                    "output_edges": node.get("output_edges", []),
                    "status": node.get("status", "pending"), # Default to pending if not specified
                    "result": None,
                    "executor_id": None
                })
            
            # Store node status in memory
            self.memory.add_data(
                data=node_status,
                data_type="node_status",
                description="Node information and execution status",
                metadata={"key": "Node_Status"}
            )
            
            # Return success message with summary
            node_count = len(plan_dag_nodes)
            edge_count = len(edge_status)
            enabled_edges = len([e for e in edge_status if e["status"] == "enabled"])
            
            return (f"PlanDAG Loaded: {os.path.basename(plan_dag_path)}\n\n"
                   f"Successfully loaded PlanDAG with {node_count} nodes and {edge_count} edges. "
                   f"{enabled_edges} edges have been enabled from start node(s). "
                   f"Edge_Status and Node_Status are now available in memory.")
            
        except Exception as e:
            return f"Error loading PlanDAG: {str(e)}" 
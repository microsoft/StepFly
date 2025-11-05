import os
import json
from typing import Dict, Any, Optional, List
from abc import ABC, abstractmethod
import importlib
import re

from stepfly.utils.config_loader import config
from stepfly.tools.base_tool import BaseTool
from stepfly.utils.memory import Memory

class BasePlugin(ABC):
    """
    Base class for all plugins extracted from TSG documents.
    Each plugin represents a functional code snippet from a TSG document.
    """
    
    def __init__(self, plugin_id: str, description: str, source_tsg: str, language: str = "txt"):
        """
        Initialize the plugin
        
        Args:
            plugin_id: Unique identifier for the plugin
            description: Description of what the plugin does and its parameters
            source_tsg: Name of the TSG that this plugin belongs to
            language: Programming language or format of the code
        """
        self.plugin_id = plugin_id
        self.description = description
        self.source_tsg = source_tsg
        self.language = language
        
        # Store config for tool access
        self.config = config
    
    @abstractmethod
    def execute(self, **kwargs) -> str:
        """
        Execute the plugin with the given parameters
        
        Args:
            **kwargs: Parameters for the plugin
            
        Returns:
            Result of the plugin execution (code snippet ID to be retrieved from memory)
        """
        pass
    
    def get_description(self) -> Dict[str, Any]:
        """
        Get a structured description of the plugin
        
        Returns:
            Plugin metadata and description
        """
        return {
            "plugin_id": self.plugin_id,
            "description": self.description,
            "source_tsg": self.source_tsg,
            "language": self.language
        }
    
    def get_formatted_description(self) -> str:
        """
        Get a human-readable description of this plugin
        
        Returns:
            Formatted description string
        """
        return f"{self.plugin_id}: {self.description} [Language: {self.language}]"
    
    @classmethod
    def create_tool_from_plugin(cls, plugin, session_id, memory, tool_name: str = None) -> BaseTool:
        """
        Create a tool that wraps a plugin
        
        Args:
            plugin: Plugin instance to wrap
            tool_name: Name for the tool (defaults to plugin_id + '_tool')
            
        Returns:
            Tool instance that executes the plugin
        """
        from stepfly.tools.base_tool import BaseTool
        
        if not tool_name:
            tool_name = f"{plugin.plugin_id}_tool"
        
        # Create a tool class dynamically
        class PluginTool(BaseTool):
            def __init__(
                self,
                session_id: str,
                memory: Memory,
                tool_name: str,
                plugin: "BasePlugin",
                description: Optional[str] = None
            ):
                super().__init__(session_id=session_id, memory=memory)
                self.name = tool_name
                self.description = description
                self.plugin = plugin
                
            def execute(self, **kwargs) -> str:
                # Execute the plugin to get the snippet
                snippet = self.plugin.execute(**kwargs)

                # Check if the result is an error message BEFORE storing
                if snippet.startswith("Error:") or snippet.startswith("Missing required parameter:"):
                    return snippet

                # Store the formatted query in memory and return the key
                snippet_id = self.memory.store_code_snippet(
                    code=snippet,
                    plugin_id=self.plugin.plugin_id,
                    tsg_name=self.plugin.source_tsg,
                    parameters=kwargs,
                    description=f"Query/code generated from TSG {self.plugin.source_tsg}"
                )

                # Return the snippet ID for later retrieval
                return f"SQL query snippet stored with ID: {snippet_id}"

        return PluginTool(
            session_id=session_id,
            memory=memory,
            tool_name=tool_name,
            description=f"{plugin.description} Usage: {tool_name} with parameters",
            plugin=plugin
        )
    
    @classmethod
    def get_plugins_for_tsg(cls, tsg_name: str) -> List["BasePlugin"]:
        """
        Get all plugins for a TSG
        
        Args:
            tsg_name: Name of the TSG
            
        Returns:
            List of plugin instances
        """
        plugins = []
        plugins_dir = os.path.join("plugins", tsg_name)
        
        if not os.path.exists(plugins_dir):
            return []
        
        # Get plugin files
        plugin_files = [f for f in os.listdir(plugins_dir) 
                       if f.endswith('.py') and f != '__init__.py']
        
        def natural_sort_key(s):
            return [int(text) if text.isdigit() else text.lower() 
                    for text in re.split(r'(\d+)', s)]
        
        plugin_files.sort(key=natural_sort_key)
        
        for plugin_file in plugin_files:
            plugin_id = plugin_file[:-3]  # Remove .py extension
            
            # Import the plugin module
            module = importlib.import_module(f"plugins.{tsg_name}.{plugin_id}")

            # Find the plugin class
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if (isinstance(attr, type) and
                    issubclass(attr, cls) and
                    attr is not cls):
                    # Create an instance and add to list
                    plugins.append(attr())
                    break

        return plugins
    

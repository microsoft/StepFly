from abc import ABC, abstractmethod
import os
import contextlib
from stepfly.utils.memory import Memory

class BaseTool(ABC):
    """
    Base class for all tools used by agents.
    Tools provide specific functionality like reading files,
    interacting with users, or executing commands.
    """
    
    def __init__(self, session_id: str, memory: Memory):
        """
        Initialize a tool
        
        Args:
            name: Tool name for identification
            description: Tool description for prompts
        """
        self.name = None
        self.description = None
        self.session_id = session_id
        self.memory = memory
        # Store the project root directory
        self.project_root = self._get_project_root()
    
    @abstractmethod
    def execute(self, **kwargs) -> str:
        """
        Execute the tool functionality
        
        Args:
            **kwargs: Tool-specific parameters
            
        Returns:
            Result of the tool execution as a string
        """
        pass
    
    def get_description(self) -> str:
        """
        Get a formatted description of the tool for prompts
        
        Returns:
            Formatted tool description
        """
        return f"{self.name}: \n{self.description}"
    
    def _get_project_root(self) -> str:
        """
        Get the project root directory
        
        Returns:
            Path to the project root directory
        """
        # Get the current file's directory
        current_dir = os.path.dirname(os.path.abspath(__file__))
        # The parent directory of tools is the project root
        return os.path.dirname(current_dir)
    
    @contextlib.contextmanager
    def with_project_root_as_cwd(self):
        """
        Context manager to temporarily change the working directory to the project root
        """
        # Save the current working directory
        orig_cwd = os.getcwd()
        
        try:
            # Change to the project root directory
            os.chdir(self.project_root)
            yield
        finally:
            # Restore the original working directory
            os.chdir(orig_cwd)

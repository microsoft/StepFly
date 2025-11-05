from typing import Dict, Any, Optional

from rich.console import Console
from rich.prompt import Prompt

from stepfly.utils.memory import Memory
from stepfly.tools.base_tool import BaseTool

class UserInteraction(BaseTool):
    """Tool for interacting with users"""
    
    def __init__(self, session_id: str, memory: Memory):
        super().__init__(session_id, memory)
        self.name="user_interaction"
        self.description=(
            "Interact with the user to gather information, provide updates, or get user choices.\n\n"
            "Required Parameters:\n"
            "- message: Text to display to the user\n\n"
            "Optional Parameters:\n"
            "- type: Type of interaction (\"info\", \"question\", or \"options\", default: \"info\")\n"
            "- options: List of options for type=\"options\""
        )
        self.console = Console()
    
    def execute(self, message: str, type: str = "info", options: Optional[list] = None) -> str:
        """
        Interact with the user
        
        Args:
            message: Message to show to the user
            type: Type of interaction (info, question, options)
            options: List of options for type=options
            
        Returns:
            User response or confirmation message
        """
        try:
            if type == "info":
                self.console.print(f"\n[bold blue]Info:[/bold blue] {message}")
                return "Message displayed to user."
                
            elif type == "question":
                response = Prompt.ask(f"\n[bold blue]Question:[/bold blue] {message}")
                return f"User response: {response}"
                
            elif type == "options":
                if not options or not isinstance(options, list):
                    return "Error: options parameter must be a non-empty list for type=options"
                    
                self.console.print(f"\n[bold blue]Options:[/bold blue] {message}")
                for i, option in enumerate(options, 1):
                    self.console.print(f"{i}. {option}")
                    
                choice = Prompt.ask("Enter your choice (number)")
                try:
                    choice_idx = int(choice) - 1
                    if 0 <= choice_idx < len(options):
                        return f"User selected: {options[choice_idx]}"
                    else:
                        return f"Invalid choice. Please select a number between 1 and {len(options)}."
                except ValueError:
                    return "Invalid input. Please enter a number."
            else:
                return f"Unsupported interaction type: {type}"
        except Exception as e:
            return f"Error during user interaction: {str(e)}" 
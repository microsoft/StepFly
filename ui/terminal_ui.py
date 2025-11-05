import uuid
import argparse
from datetime import datetime

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
import os
import sys

# Add project root path to Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from stepfly.agents.scheduler import Scheduler
from stepfly.utils.memory import Memory


class TerminalUI:
    """
    Terminal UI for the TSG Agent
    This class is responsible for the terminal UI and the interaction with the user.
    """
    def __init__(self):
        self.console = Console()
        self.mode = "online"
    


    def start_online_mode(self, incident_id:str = None) -> str:
        """Start the online mode interface"""
        
        self.console.print(
            Panel.fit(
                "[bold cyan]Online Mode[/bold cyan]\n"
                "This mode helps you troubleshoot incidents using existing TSG knowledge.",
                title="TSG Executor",
                border_style="cyan",
            )
        )

        # clear the memory database
        # Memory.reset_database()
        _timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        if incident_id is not None:
            session_id = f"{incident_id}_session-{_timestamp}_{str(uuid.uuid4())[0:8]}"
            memory = Memory(session_id=session_id)
            scheduler = Scheduler(session_id=session_id, memory=memory)

            scheduler.start_session(incident_id=incident_id)
        else:
            session_id = f"session-{_timestamp}_{str(uuid.uuid4())[0:8]}"
            memory = Memory(session_id=session_id)
            scheduler = Scheduler(session_id=session_id, memory=memory)

            scheduler.start_session()
        
        return session_id


def main():
    """
    TSG Agent Terminal Interface
    A LLM-based agent system for troubleshooting and TSGs management
    """
    parser = argparse.ArgumentParser(
        description='TSG Agent Terminal Interface',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        '--incident-id',
        type=str,
        help='Incident ID to start troubleshooting session with'
    )
    
    args = parser.parse_args()
    
    console = Console()
    
    # Display welcome message
    console.print(
        Panel.fit(
            "[bold blue]Welcome to TSG Agent[/bold blue]\n"
            "A LLM-based agent system for troubleshooting and TSGs management",
            title="TSG Agent Terminal",
            border_style="blue",
        )
    )
    
    # Get incident ID from args or prompt user
    incident_id = args.incident_id
    if not incident_id:
        incident_id = Prompt.ask(
            "[bold]Enter Incident ID (optional):[/bold]",
            default=""
        ).strip()
        
        # Allow empty incident ID for general troubleshooting
        if not incident_id:
            incident_id = None
    
    # Start the terminal UI
    ui = TerminalUI()
    ui.start_online_mode(incident_id)


if __name__ == "__main__":
    main()
    
#!/usr/bin/env python3
"""
StepFly Dashboard API
Provides REST API endpoints for real-time UI visualization
Enhanced with scheduler integration and user interaction
"""

import json
import os
import sys
import uuid
import threading
import queue
from typing import Dict, Any, Optional, List
from datetime import datetime

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from stepfly.utils.memory import Memory
from stepfly.agents.scheduler import Scheduler


class TSGVisualizationAPI:
    """API for providing visualization data and managing TSG execution"""
    
    def __init__(self):
        """Initialize API without session ID"""
        self.session_id = None
        self.memory = None
        self.scheduler = None
        self.scheduler_thread = None
        self.scheduler_conversation = []  # Store scheduler conversation history
        self.user_input_queue = queue.Queue()  # Queue for user inputs
        self.waiting_for_input = False
        self.input_prompt = ""
    
    def start_new_session(self) -> Dict[str, Any]:
        """Start a new TSG execution session without incident ID"""
        try:
            # Generate session ID
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            session_uuid = str(uuid.uuid4())[:8]
            self.session_id = f"session-{timestamp}_{session_uuid}"
            
            # Clear previous conversation
            self.scheduler_conversation = []
            
            # Initialize memory with new session
            self.memory = Memory(session_id=self.session_id)
            
            # Initialize scheduler
            self.scheduler = Scheduler(session_id=self.session_id, memory=self.memory)
            
            # Add initial conversation message
            self.scheduler_conversation.append({
                "role": "system",
                "content": f"🚀 New StepFly session started",
                "timestamp": datetime.now().isoformat()
            })
            
            # Setup message capturing
            self._setup_message_capture()
            
            # Start scheduler in background thread
            self.scheduler_thread = threading.Thread(
                target=self._run_scheduler,
                daemon=True
            )
            self.scheduler_thread.start()
            
            return {
                "success": True,
                "session_id": self.session_id,
                "message": "Session started successfully"
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
    
    def _setup_message_capture(self):
        """Setup hooks to capture scheduler messages and user interactions"""
        # Store original methods
        original_display_message = self.scheduler.display_message
        
        # Override display_message to capture scheduler outputs (emit all without filtering)
        def capture_message(message, title=None, style="blue"):
            self.scheduler_conversation.append({
                "role": "scheduler",
                "content": message,
                "title": title,
                "style": style,
                "timestamp": datetime.now().isoformat()
            })
            # Call original display method
            original_display_message(message, title, style)
        
        self.scheduler.display_message = capture_message
        
        # Override the user_interaction tool if it exists
        if hasattr(self.scheduler, 'tools') and 'user_interaction' in self.scheduler.tools:
            original_tool = self.scheduler.tools['user_interaction']
            original_execute = original_tool.execute
            
            def wrapped_user_interaction(message: str, type: str = "info", options = None) -> str:
                # Add prompt to conversation
                if type == "question":
                    self.scheduler_conversation.append({
                        "role": "tool",
                        "content": f"❓ {message}",
                        "timestamp": datetime.now().isoformat()
                    })
                    
                    # Set flag for frontend
                    self.waiting_for_input = True
                    self.input_prompt = message
                    
                    # Wait for user input via queue
                    try:
                        user_input = self.user_input_queue.get(timeout=300)  # 5 minute timeout
                    except:
                        user_input = ""
                    
                    # Clear flag
                    self.waiting_for_input = False
                    self.input_prompt = ""
                    
                    # Add user response to conversation
                    self.scheduler_conversation.append({
                        "role": "user",
                        "content": user_input,
                        "timestamp": datetime.now().isoformat()
                    })
                    
                    return f"User response: {user_input}"
                else:
                    # For info messages, just display them
                    self.scheduler_conversation.append({
                        "role": "tool",
                        "content": f"ℹ️ {message}",
                        "timestamp": datetime.now().isoformat()
                    })
                    return "Message displayed to user."
            
            # Replace the execute method of user_interaction tool
            original_tool.execute = wrapped_user_interaction
    
    def _run_scheduler(self):
        """Run scheduler in background thread"""
        try:
            # Start session - this will trigger user_interaction for incident ID
            self.scheduler.start_session()
            
            # After scheduler finishes, if it produced a final conclusion, surface it explicitly
            try:
                session_state = getattr(self.scheduler, 'session_state', {}) or {}
                conclusion = session_state.get('troubleshooting_conclusion')
                if conclusion:
                    # Format conclusion for human-readable display
                    if isinstance(conclusion, dict):
                        # Render simple key-value list
                        lines = []
                        for k, v in conclusion.items():
                            lines.append(f"- {k}: {v}")
                        formatted = "\n".join(lines)
                    else:
                        formatted = str(conclusion)
                    
                    self.scheduler_conversation.append({
                        "role": "scheduler",
                        "title": "🔍 Troubleshooting Conclusion",
                        "content": formatted,
                        "style": "green",
                        "timestamp": datetime.now().isoformat()
                    })
                else:
                    # If no explicit conclusion, still notify completion
                    self.scheduler_conversation.append({
                        "role": "scheduler",
                        "content": "✅ Troubleshooting session finished.",
                        "style": "green",
                        "timestamp": datetime.now().isoformat()
                    })
            except Exception:
                # Do not break the UI if formatting fails
                pass
                
        except Exception as e:
            self.scheduler_conversation.append({
                "role": "error",
                "content": f"❌ Scheduler error: {str(e)}",
                "timestamp": datetime.now().isoformat()
            })
    
    def get_scheduler_conversation(self) -> Dict[str, Any]:
        """Get scheduler conversation history"""
        return {
            "success": True,
            "conversation": self.scheduler_conversation,
            "waiting_for_input": self.waiting_for_input,
            "input_prompt": self.input_prompt,
            "session_id": self.session_id
        }
    
    def send_user_input(self, user_input: str) -> Dict[str, Any]:
        """Send user input to scheduler"""
        try:
            if not self.waiting_for_input:
                return {
                    "success": False,
                    "error": "No input expected at this time"
                }
            
            # Put input in queue for scheduler thread
            self.user_input_queue.put(user_input)
            
            return {
                "success": True,
                "message": "Input received and sent to scheduler"
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
    
    def get_realtime_status(self) -> Dict[str, Any]:
        """Get current execution status from Memory"""
        if not self.memory:
            return {
                "success": False,
                "error": "No session active"
            }
        
        try:
            node_status = self.memory.get_data_by_key("Node_Status") or []
            edge_status = self.memory.get_data_by_key("Edge_Status") or []
            
            # Get PlanDAG structure if available
            plandag_nodes = self._extract_plandag_from_memory()
            
            # Get incident info
            incident_info = self.memory.get_data_by_key("incident_info") or ""
            
            # Calculate statistics
            stats = self._calculate_statistics(node_status)
            
            return {
                "success": True,
                "session_id": self.session_id,
                "timestamp": datetime.now().isoformat(),
                "node_status": node_status,
                "edge_status": edge_status,
                "plandag_nodes": plandag_nodes,
                "incident_info": incident_info,
                "statistics": stats
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "session_id": self.session_id,
                "timestamp": datetime.now().isoformat()
            }
    
    def _extract_plandag_from_memory(self) -> List[Dict[str, Any]]:
        """Extract PlanDAG structure from Memory data"""
        # Try to get stored PlanDAG structure
        # In the system, PlanDAG is loaded and nodes are stored in Node_Status
        node_status = self.memory.get_data_by_key("Node_Status") or []
        
        # Build PlanDAG structure from node_status
        plandag_nodes = []
        for node in node_status:
            plandag_node = {
                "node": node.get("node", ""),
                "description": node.get("description", ""),
                "input_edges": node.get("input_edges", []),
                "output_edges": node.get("output_edges", [])
            }
            plandag_nodes.append(plandag_node)
            
        return plandag_nodes
    
    def _calculate_statistics(self, node_status: List[Dict]) -> Dict[str, int]:
        """Calculate execution statistics"""
        stats = {
            "total_nodes": len(node_status),
            "pending": 0,
            "running": 0,
            "finished": 0,
            "failed": 0,
            "skipped": 0
        }
        
        for node in node_status:
            status = node.get("status", "pending")
            if status in stats:
                stats[status] += 1
                
        return stats
    
    def get_node_conversation(self, node_id: str) -> Dict[str, Any]:
        """Get conversation history for a specific node"""
        if not self.memory:
            return {
                "success": False,
                "error": "No session active"
            }
        
        try:
            # Find the node in Node_Status
            node_status = self.memory.get_data_by_key("Node_Status") or []
            target_node = None
            
            for node in node_status:
                if node.get("node") == node_id:
                    target_node = node
                    break
            
            if not target_node:
                return {
                    "success": False,
                    "error": f"Node {node_id} not found"
                }
            
            # Get executor_id from the node
            executor_id = target_node.get("executor_id")
            if not executor_id:
                return {
                    "success": True,
                    "node_id": node_id,
                    "conversation": [],
                    "message": "Node has not been executed yet"
                }
            
            # Get conversation from Memory using executor_id
            conversation = self.memory.get_agent_context(executor_id, message_only=True)
            
            # Get execution result
            executor_result = self.memory.get_data_by_key(f"{executor_id}_step_result")
            
            # Format conversation for frontend display
            formatted_conversation = self._format_conversation(conversation)
            
            return {
                "success": True,
                "node_id": node_id,
                "executor_id": executor_id,
                "conversation": formatted_conversation,
                "execution_result": executor_result,
                "node_info": {
                    "status": target_node.get("status"),
                    "description": target_node.get("description"),
                    "result": target_node.get("result")
                }
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
    
    def _format_conversation(self, conversation: List[Dict]) -> List[Dict]:
        """Format conversation for frontend display"""
        if not conversation:
            return []
        
        formatted = []
        for msg in conversation:
            role = msg.get("role", "")
            content = msg.get("content", "")
            
            # Parse assistant messages that are in JSON format
            if role == "assistant":
                try:
                    parsed_content = json.loads(content)
                    formatted_msg = {
                        "role": role,
                        "content": content,
                        "parsed": {
                            "thought": parsed_content.get("thought", ""),
                            "action": parsed_content.get("action", ""),
                            "parameters": parsed_content.get("parameters", {})
                        }
                    }
                except (json.JSONDecodeError, TypeError):
                    formatted_msg = {
                        "role": role,
                        "content": content,
                        "parsed": None
                    }
            else:
                formatted_msg = {
                    "role": role,
                    "content": content
                }
            
            formatted.append(formatted_msg)
        
        return formatted
    
    def get_edge_connections(self) -> Dict[str, Any]:
        """Get edge connection information for graph rendering"""
        if not self.memory:
            return {
                "success": False,
                "error": "No session active"
            }
        
        try:
            edge_status = self.memory.get_data_by_key("Edge_Status") or []
            node_status = self.memory.get_data_by_key("Node_Status") or []
            
            # Build edge connections with source and target
            connections = []
            for edge in edge_status:
                edge_name = edge.get("edge", "")
                
                # Find source and target nodes
                source = None
                target = None
                
                for node in node_status:
                    # Check output edges for source
                    for out_edge in node.get("output_edges", []):
                        if out_edge.get("edge") == edge_name:
                            source = node.get("node")
                            
                    # Check input edges for target
                    for in_edge in node.get("input_edges", []):
                        if in_edge.get("edge") == edge_name:
                            target = node.get("node")
                
                if source and target:
                    connections.append({
                        "edge": edge_name,
                        "source": source,
                        "target": target,
                        "status": edge.get("status", "pending"),
                        "condition": self._get_edge_condition(node_status, edge_name)
                    })
            
            return {
                "success": True,
                "connections": connections
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
    
    def _get_edge_condition(self, node_status: List[Dict], edge_name: str) -> str:
        """Get condition for an edge from node definitions"""
        for node in node_status:
            for out_edge in node.get("output_edges", []):
                if out_edge.get("edge") == edge_name:
                    return out_edge.get("condition", "")
        return ""
    
    def get_session_info(self) -> Dict[str, Any]:
        """Get session information"""
        if not self.memory:
            return {
                "success": False,
                "error": "No session active"
            }
        
        try:
            incident_info = self.memory.get_data_by_key("incident_info") or ""
            tsg_content = self.memory.get_data_by_key("tsg_content") or ""
            
            # Extract TSG name from content if available
            tsg_name = "Unknown TSG"
            if tsg_content:
                lines = tsg_content.split('\n')
                for line in lines[:10]:  # Check first 10 lines
                    if line.startswith('#'):
                        tsg_name = line.replace('#', '').strip()
                        break
            
            return {
                "success": True,
                "session_id": self.session_id,
                "incident_info": incident_info[:500] if incident_info else "No incident info",  # Truncate for display
                "tsg_name": tsg_name,
                "is_active": self.scheduler_thread and self.scheduler_thread.is_alive() if self.scheduler_thread else False
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

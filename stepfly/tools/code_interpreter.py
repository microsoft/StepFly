import contextlib
import datetime
import importlib
import io
import json
import re
import traceback
import types
from typing import Dict, Any, Optional, List

import numpy as np
import pandas as pd
import pymongo
import pymongoarrow as pma
import scipy
from rich.console import Console
from rich.panel import Panel

from stepfly.agents.base_agent import BaseAgent
from stepfly.utils.memory import Memory
from stepfly.utils.config_loader import config
from stepfly.prompts import Prompts
from stepfly.tools.base_tool import BaseTool
from stepfly.utils.trace_logger import save_agent_trace  # Add trace logger import


def _format_success_response(code: str, result: str, include_code: bool = False) -> str:
    """Format a successful code execution response"""
    response = "Code executed successfully:\n"
    if include_code:
        response += "```python\n"
        response += code.strip()
        response += "\n```\n\n"

    response += "```\n"
    response += result.strip() if result.strip() else "[No output]"
    response += "\n```"

    return response


def _format_error_response(code: str, error: str, attempts: int) -> str:
    """Format an error response after all attempts failed"""
    response = f"Failed to execute code after {attempts} attempts.\n\n"
    response += "Last code attempted:\n"
    response += "```python\n"
    response += code.strip()
    response += "\n```\n\n"

    response += "Error:\n"
    response += "```\n"
    response += error.strip()
    response += "\n```\n\n"

    response += "Please try again with a more specific task description or simpler requirements."

    return response


class CodeInterpreter(BaseTool):
    """Tool for writing and executing Python code to analyze data and perform computations"""
    

    def __init__(self, session_id: str, memory: Memory):
        super().__init__(session_id, memory)
        self.name="code_interpreter"
        self.description=(
            "Write and execute Python code to analyze data and perform computations. "
            "Supports stateful execution and memory data integration.\n\n"

            "## Required Parameters\n"
            "- **task** (string): Description of the task to accomplish\n\n"
            "- **input_type**: Type of input data, can be either (cannot mix both types in one call):\n"
            "  • `memory_data`: Data stored in memory, referenced by GUIDs\n"
            "  • `direct_data`: Direct data provided as a dictionary\n\n"
            "- **input_data**: Data to process, can be either:\n"
            "  • Dictionary mapping exact memory data_ids (GUIDs) to descriptions when data is stored in memory\n"
            "  • Dictionary of direct data (e.g., lists, dictionaries) where keys are variable names and values are the data. In this case, be more specific about the variable names. Do not use names like `data`, `df`, etc. The value should be simple data types like lists, dictionaries, or strings in JSON format which will be parsed into Python objects.\n\n"

            "## Usage Examples\n"
            "**With memory data as input where the keys are data GUIDs:**\n"
            "```json\n"
            "{\n"
            "  \"task\": \"Compare metrics across environments\",\n"
            "  \"input_type\": \"memory_data\",\n"
            "  \"input_data\": {\n"
            "    \"88f7e390-af9a-4cf8-a6e1-a3b609913ac9\": \"Production metrics\",\n"
            "    \"54321abc-def0-1234-5678-abcdef123456\": \"Staging metrics\"\n"
            "  }\n"
            "}\n"
            "```\n\n"
            "**With direct data as input:**\n"
            "```json\n"
            "{\n"
            "  \"task\": \"Calculate average response time for API calls\",\n"
            "  \"input_type\": \"direct_data\",\n"
            "  \"input_data\": {\"response_time_list\": [100, 200, 150, 300, 250]}\n"
            "}\n"
            "```\n\n"

            "## Output\n"
            "- Executed code\n"
            "- Printed output from code execution\n"
            "- Error messages with debugging information if execution fails\n\n"

            "## Notes\n"
            "- **Output Requirement**: Use print() statements for all output - only printed text is visible\n"
            "- **Visualization**: No visualization libraries (matplotlib) - provide textual summaries\n"
            "- **DataFrame Access**: DataFrames from memory are pre-loaded and ready to use\n"
            "- **Allowed Modules**: pandas, numpy, scipy, datetime, re, json, math, statistics"
        )
        # Safe modules that can be imported by default
        self.allowed_modules = config.get("tools.code_interpreter.allowed_modules", [
            "pandas", "numpy", "scipy", "datetime", "re", "json", 
            "math", "statistics", "collections", "itertools", "pymongo",
            "pymongoarrow", "pyarrow"
        ])
        
        # Get max attempts from config
        self.max_attempts = config.get("tools.code_interpreter.max_attempts", 3)
        
        # Create a mini LLM agent for code generation
        self.code_agent = CodeGeneratorAgent(session_id=session_id)
    
    def execute(self, task: str, input_type: str, input_data: Any = None) -> str:
        """
        Execute the code interpreter to generate and run code
        
        Args:
            task: Description of what the code should accomplish
            input_type: Type of input data, either 'memory_data' or 'direct_data'
            input_data: Either a dictionary mapping data_ids to descriptions or direct data
            
        Returns:
            Results of code execution
        """
        # Create a unique execution ID for this session
        execution_id = f"code_interpreter_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}_{id(self)}"
        
        # Initialize execution state
        execution_state = {
            "task": task,
            "input_data": input_data,
            "start_time": datetime.datetime.now().isoformat(),
            "status": "started",
            "attempts": []
        }
        
        # Save initial trace
        save_agent_trace(
            session_id=self.session_id,
            agent_type="code_interpreter",
            agent_id=execution_id,
            data={
                "execution_state": execution_state,
                "status": "initialized"
            }
        )
        
        # Initialize variables
        data_info = {}
        data_values = {}
        
        # Process input_data depending on its type
        if input_type == "memory_data":
            # First type: Dictionary mapping data_ids to descriptions
            for data_id, description in input_data.items():
                data = self.memory.get_data(data_id)
                if data is not None and isinstance(data, pd.DataFrame):
                    # Create a valid Python variable name from GUID
                    var_name = f"data_{data_id.replace('-', '_')}"

                    # Store DataFrame for execution environment
                    data_values[var_name] = data

                    # Create data info for the code generator
                    data_info[var_name] = {
                        "data_id": data_id,
                        "description": description,
                        "data_type": "dataframe",
                        "shape": list(data.shape),
                        "columns": list(data.columns),
                        "samples": data.head(5).to_dict(orient='records')
                    }
                elif data is not None:
                    # For non-DataFrame data
                    var_name = f"data_{data_id.replace('-', '_')}"

                    # Store for execution environment
                    data_values[var_name] = data

                    data_info[var_name] = {
                        "data_id": data_id,
                        "description": description,
                        "data_type": "other",
                        "data_preview": str(data)[:1000] + "..." if isinstance(data, str) and len(str(data)) > 1000 else str(data)
                    }
                else:
                    raise ValueError(
                        f"Data with ID '{data_id}' not found in memory. Please check the data_id."
                    )
        elif input_type == "direct_data":
            for var_name, value in input_data.items():
                data_values[var_name] = value

                data_info[var_name] = {
                    "data_type": type(value).__name__,
                    "description": f"Directly provided data for variable '{var_name}'",
                    "data_preview": str(value)[:1000] + "..." if isinstance(value, str) and len(str(value)) > 1000 else str(value)
                }
        else:
            raise ValueError("Invalid input_type. Must be either 'memory_data' or 'direct_data'.")

        
        attempt = 0
        last_error = None
        last_llm_context = None
        previous_code = None
        code = None
        
        while attempt < self.max_attempts:
            attempt += 1
            
            # Create attempt record
            attempt_record = {
                "attempt_number": attempt,
                "start_time": datetime.datetime.now().isoformat()
            }
            
            # 1. Generate code using the code agent
            # Get TSG content from memory for context
            tsg_content = self.memory.get_data_by_key("tsg_content")
            code_args = {
                "task": task,
                "input_data": input_data,
                "data_info": data_info,
                "attempt_number": attempt,
                "tsg_content": tsg_content,
                "previous_code": previous_code  # Pass previous code for context
            }
            
            if last_error:
                code_args["error"] = last_error
                
            code_result = self.code_agent.generate_code(**code_args)
            code = code_result["code"]
            previous_code = code  # Save for next iteration
            attempt_record["generated_code"] = code
            attempt_record["llm_context"] = code_result["llm_context"]
            last_llm_context = code_result["llm_context"]  # Save for final trace
            
            # Save trace after code generation
            execution_state["attempts"].append(attempt_record)
            save_agent_trace(
                session_id=self.session_id,
                agent_type="code_interpreter",
                agent_id=execution_id,
                data={
                    "execution_state": execution_state,
                    "current_attempt": attempt,
                    "generated_code": code,
                    "llm_context": code_result["llm_context"],
                    "status": "code_generated"
                }
            )
            
            # 2. Execute the code with pre-loaded data if available
            result, error = self._execute_code(code, self.allowed_modules, preloaded_data=data_values)

            # Update attempt record with results
            attempt_record["result"] = result
            attempt_record["error"] = error
            attempt_record["end_time"] = datetime.datetime.now().isoformat()
            
            # Save trace after code execution
            save_agent_trace(
                session_id=self.session_id,
                agent_type="code_interpreter",
                agent_id=execution_id,
                data={
                    "execution_state": execution_state,
                    "current_attempt": attempt,
                    "execution_result": result,
                    "execution_error": error,
                    "llm_context": code_result["llm_context"],
                    "status": "code_executed"
                }
            )
            
            # 3. If successful, return the result
            if not error:
                # Format successful response
                formatted_result = _format_success_response(code, result)
                
                # Save final successful trace
                execution_state["status"] = "completed_success"
                execution_state["end_time"] = datetime.datetime.now().isoformat()
                execution_state["final_result"] = formatted_result
                
                save_agent_trace(
                    session_id=self.session_id,
                    agent_type="code_interpreter",
                    agent_id=execution_id,
                    data={
                        "execution_state": execution_state,
                        "status": "completed",
                        "final_result": formatted_result,
                        "final_llm_context": last_llm_context
                    }
                )
                
                return formatted_result
            
            # 4. Otherwise, store the error and try again
            last_error = error
        
        # All attempts failed - format error response
        error_response = _format_error_response(code, last_error, attempt)
        
        # Save final failure trace
        execution_state["status"] = "completed_failure"
        execution_state["end_time"] = datetime.datetime.now().isoformat()
        execution_state["final_error"] = error_response
        
        save_agent_trace(
            session_id=self.session_id,
            agent_type="code_interpreter",
            agent_id=execution_id,
            data={
                "execution_state": execution_state,
                "status": "failed",
                "final_error": error_response,
                "final_llm_context": last_llm_context
            }
        )
        
        return error_response
    
    def _execute_code(self, code: str, allowed_modules: List[str], preloaded_data: Dict[str, Any] = None) -> tuple:
        """
        Execute generated code in a controlled environment
        
        Args:
            code: Python code to execute
            allowed_modules: Modules that can be imported
            preloaded_data: Dictionary of data_id -> DataFrame/data for execution
            
        Returns:
            Tuple of (result, error_message)
        """
        # Create string IO for capturing output
        stdout_capture = io.StringIO()
        stderr_capture = io.StringIO()
        
        # Try to load previous state
        session_vars = {}
        
        # Prepare the execution environment
        exec_globals = {
            "pd": pd,
            "np": np,
            "scipy": scipy,
            "re": re,
            "datetime": datetime,
            "json": json,
            "pymongo": pymongo,
            "pma": pma,  # PyMongoArrow
            "memory": self.memory,  # Provide access to the memory system
            "__builtins__": __builtins__,
            "print": lambda *args, **kwargs: print(*args, **kwargs, file=stdout_capture),
            # Add previous session variables to environment
            **session_vars
        }
        
        # Add data frames from memory if available
        if preloaded_data:
            exec_globals.update(preloaded_data)
        
        # Import allowed modules
        for module_name in allowed_modules:
            if module_name not in ["pd", "np", "scipy", "re", "datetime", "json", "pymongo", "pma"]:  # Already imported
                exec_globals[module_name] = importlib.import_module(module_name)
        
        try:
            # Capture all output
            with contextlib.redirect_stdout(stdout_capture), contextlib.redirect_stderr(stderr_capture):
                # Execute the code
                exec(code, exec_globals)
                
                # Save state for next execution
                # Filter out modules, functions, and special variables
                reserved_vars = ['pd', 'np', 're', 'datetime', 'json', 'pymongo', 'pma', 'memory', 'print']
                if preloaded_data:
                    reserved_vars.extend(list(preloaded_data.keys()))
                
            # Get the output
            stdout = stdout_capture.getvalue()
            
            # Print the output prominently to terminal with rich formatting
            if stdout.strip():
                console = Console()
                console.print("\n")
                console.print(Panel(
                    stdout,
                    title="[bold cyan]CODE EXECUTION RESULT[/bold cyan]",
                    border_style="green",
                    expand=False
                ))
                console.print("\n")
            
            # Return the result
            return stdout, None
            
        except Exception as e:
            # Get the error details
            error_type = type(e).__name__
            error_msg = str(e)
            tb = traceback.format_exc()
            
            # Print the error prominently to terminal with rich formatting
            console = Console()
            console.print("\n")
            console.print(Panel(
                f"[bold red]{error_type}:[/bold red] {error_msg}\n\n{tb}",
                title="[bold red]CODE EXECUTION ERROR[/bold red]",
                border_style="red",
                expand=False
            ))
            console.print("\n")
            
            return None, f"{error_type}: {error_msg}\n\n{tb}"


class CodeGeneratorAgent(BaseAgent):
    """
    Agent for generating Python code. This is a lightweight agent that doesn't
    maintain conversation history in the memory.
    """
    
    def __init__(self, session_id: str = None):
        super().__init__(session_id=session_id)
        self.name = "code_generator"
        self.role = "code_generator"
    
    def generate_code(self, task: str, input_data: Any = None, 
                     data_info: Dict = None, error: Optional[str] = None, 
                     attempt_number: int = 1, tsg_content: str = None,
                      previous_code: str = None) -> Dict[str, Any]:
        """
        Generate Python code based on the given task
        
        Args:
            task: Description of what the code should accomplish
            input_data: Input data that the code will process
            data_info: Information about the data stored in memory
            error: Error message from previous attempt (if any)
            attempt_number: Current attempt number
            tsg_content: TSG document content for context (optional)
            previous_code: Code from the previous attempt (if any)
            
        Returns:
            Dictionary containing generated code and the LLM context
        """
        # Build the prompt
        messages = [
            {"role": "system", "content": Prompts.code_interpreter_system_prompt()}
        ]

        # Add TSG context if available
        if tsg_content:
            messages.append(
                {"role": "system",
                 "content": f"The following is the content of the Troubleshooting Guide (TSG) that provides context for your task:\n\n{tsg_content}"}
            )

        # Construct the user message
        user_message = f"# Task: {task}\n# Attempt: {attempt_number}\n\n"
        
        # Add information about the data loaded from memory
        if data_info:
            user_message += "# Data available for analysis:\n\n"
            user_message += ("IMPORTANT: The following data has been PRE-LOADED into global variables.\n"
                             "DO **NOT** use memory.get_data() to access them.\n")
            user_message += "Simply use the variable names directly in your code.\n\n"
            
            for var_name, info in data_info.items():
                user_message += f"Variable Name: {var_name}\n"
                user_message += f"Description: {info.get('description', 'No description')}\n"
                
                if info.get("data_type") == "dataframe":
                    from tabulate import tabulate

                    user_message += f"Type: pandas DataFrame\n"
                    user_message += f"Shape: {info.get('shape', 'Unknown')}\n"
                    user_message += f"Columns: {info.get('columns', 'Unknown')}\n"
                    
                    # Safely serialize the samples
                    try:
                        # Use custom serializer for JSON dumps to handle timestamps
                        samples = info.get('samples', [])
                        user_message += "Sample data (first 5 rows):\n"
                        if samples:
                            user_message += tabulate(samples, headers='keys', tablefmt='grid') + "\n\n"
                        else:
                            user_message += "Empty DataFrame - no samples available\n\n"

                    except Exception as e:
                        # Fallback if serialization fails
                        user_message += "Sample data: (Could not serialize sample data)\n\n"
                else:
                    user_message += f"Type: {info.get('data_type', 'Unknown')}\n"
                    user_message += f"Preview: {info.get('data_preview', 'No preview available')}\n\n"
                
                user_message += f"✅ Access this data directly as: `{var_name}`\n"
                user_message += "=========================\n\n"
        
        # Add information about direct input data
        elif input_data is not None and not isinstance(input_data, dict):
            user_message += "Input data:\n"
            if isinstance(input_data, (dict, list)):
                user_message += f"```json\n{json.dumps(input_data, indent=2)}\n```\n\n"
            else:
                user_message += f"```\n{str(input_data)}\n```\n\n"
            
            # Add type information
            user_message += f"Data type: {type(input_data).__name__}\n\n"
            user_message += "This data is accessible as 'input_data' in your code.\n\n"
        
        # Add information about MongoDB memory access
        # TODO: remove unnecessary memory methods?
        user_message += "\n## Data Storage:\n"
        user_message += "You can store data to memory by calling the following methods:\n\n"
        user_message += "- memory.add_data(data, data_type, description) -> returns data_id\n"
        user_message += ("You only need to store data that could be useful for future tasks. "
                         "When you call `memory.add_data()`, you must return the `data_id` and print it to use it later."
                         "`data_type` is 'code_interpreter' and `description` is a short text about the data."
                         "\n\n")
        
        # If this is a retry, include the error
        if error and attempt_number > 1:
            user_message += f"Your previous attempt failed with the following error (Attempt {attempt_number-1}):\n"
            user_message += "```python\n" + previous_code + "\n```\n\n"
            user_message += f"```Execution Error:\n{error}\n```\n\n"
            
            # Provide specific guidance based on common errors
            if "ModuleNotFoundError" in error and "matplotlib" in error:
                user_message += "⚠️ IMPORTANT: matplotlib is NOT available. DO NOT use any plotting libraries.\n"
                user_message += "Instead, provide textual summaries, statistical analysis, and formatted tables.\n"
                user_message += "Use pandas DataFrame.to_string() or describe() for data presentation.\n\n"
            
            elif "KeyError" in error:
                user_message += "⚠️ KeyError detected. Please check:\n"
                user_message += "1. Column names might be different than expected\n"
                user_message += "2. Use df.columns to check available columns\n"
                user_message += "3. Consider using df.info() to understand the data structure\n\n"
            
            elif "memory.get_data" in error or "NoneType" in error:
                user_message += "⚠️ Data loading error detected. Remember:\n"
                user_message += "1. Data is PRE-LOADED into variables - use them directly\n"
                user_message += "2. DO NOT use memory.get_data() for pre-loaded data\n"
                user_message += "3. Check the variable names provided above\n\n"
            
            user_message += "Please fix the issues and provide corrected complete code.\n"
        
        messages.append({"role": "user", "content": user_message})
        
        # Call the LLM to generate code
        response = self.call_llm(messages, json_response=False)
        
        # Extract the code from the response (between ```python and ```)
        code_match = re.search(r"```(?:python)?\s*([\s\S]*?)```", response)
        if code_match:
            code = code_match.group(1).strip()
        else:
            # If no code block found, assume the entire response is code
            code = response.strip()
        
        # Return both code and the complete LLM context
        return {
            "code": code,
            "llm_context": {
                "messages": messages,
                "response": response
            }
        } 
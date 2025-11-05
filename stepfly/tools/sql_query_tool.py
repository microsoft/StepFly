import os
import sqlite3
from typing import Optional

import pandas as pd

from stepfly.tools.base_tool import BaseTool
from stepfly.utils.memory import Memory


class SQLQueryTool(BaseTool):
    """Tool for executing SQL queries against a database"""
    
    def __init__(self, session_id: str, memory: Memory):
        super().__init__(session_id, memory)
        self.name = "sql_query_tool"
        self.description = (
            "Execute SQL queries against a database.\n\n"
            "This tool allows you to:\n"
            "- Execute SQL queries directly against a SQLite database\n"
            "- Run stored SQL query snippets by their ID\n\n"
            "Required Parameters (choose one):\n"
            "- query_string: Full SQL query to execute directly\n"
            "- snippet_id: ID of a stored SQL query snippet in memory\n\n"
            "Optional Parameters:\n"
            "- database_path: Path to SQLite database file (defaults to 'demo.db')\n"
            "- result_description: Description for the stored result\n\n"
            "Example queries:\n"
            "- SELECT * FROM users WHERE created_date > '2024-01-01'\n"
            "- SELECT COUNT(*) as total_orders FROM orders\n"
            "- PRAGMA table_info(users)"
        )
        
        # Default database path
        self.default_database = "./demo_data/distributed_system.db"
        
    def execute(self, 
                query_string: Optional[str] = None,
                snippet_id: Optional[str] = None,
                database_path: Optional[str] = None,
                result_description: Optional[str] = None) -> str:
        """
        Execute a SQL query and return results
        
        Args:
            query_string: Direct SQL query string to execute
            snippet_id: ID of a stored SQL query snippet in memory
            database_path: Path to database file
            result_description: Description for the stored result
            
        Returns:
            Query results summary with memory reference or result data
        """
        try:
            # Determine what query to execute
            if snippet_id:
                # Get stored query from memory using the correct method
                sql_query = self.memory.get_code_snippet(snippet_id)
                if not sql_query:
                    return f"Error: SQL snippet with ID '{snippet_id}' not found in memory."
            elif query_string:
                sql_query = query_string
            else:
                return "Error: Please provide either 'query_string' or 'snippet_id'."
            
            # Set database path
            db_path = database_path or self.default_database
            
            # Create demo database if it doesn't exist
            if not os.path.exists(db_path):
                raise FileNotFoundError(f"Database file not found at path: {db_path}")
            
            # Execute query
            result_df = self._execute_sql_query(sql_query, db_path)
            
            if result_df is None:
                return "Query executed successfully (no results returned)."
            
            if len(result_df) == 0:
                return "Query executed successfully but returned no rows."
            
            # Always store results in memory for analysis
            result_id = self.memory.add_data(
                data=result_df,
                data_type="sql_result",
                metadata={
                    "query": sql_query,
                    "database": db_path,
                    "row_count": len(result_df),
                    "column_count": len(result_df.columns),
                    "columns": list(result_df.columns)
                },
                description=result_description or "SQL query result"
            )
            
            # Get data summary for context
            summary = self.memory.get_data_summary(result_id)
            
            # Return summary with memory reference
            return (f"Query has been successfully executed. The query results are stored in memory with ID: {result_id}\n"
                   "The description of the result is as follows:\n"
                   f"Summary:\n{summary}\n\n")
            
        except Exception as e:
            return f"Error executing SQL query: {str(e)}"
    
    def _execute_sql_query(self, query: str, db_path: str) -> Optional[pd.DataFrame]:
        """Execute SQL query against SQLite database"""
        conn = None
        try:
            conn = sqlite3.connect(db_path)
            
            # For SELECT queries, return DataFrame  
            if (query.strip().upper().startswith('SELECT') or 
                query.strip().upper().startswith('PRAGMA') or 
                query.strip().upper().startswith('WITH')):
                df = pd.read_sql_query(query, conn)
                return df
            else:
                # For other queries (INSERT, UPDATE, DELETE, etc.), execute and return None
                cursor = conn.cursor()
                cursor.execute(query)
                conn.commit()
                return None
                
        except Exception as e:
            raise e
        finally:
            if conn:
                conn.close()
    
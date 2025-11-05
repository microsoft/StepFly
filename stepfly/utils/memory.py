import logging
import threading
import uuid
from datetime import datetime
from typing import Dict, Any, Optional, List

import pandas as pd
import pymongo
from pymongoarrow.api import write, find_pandas_all

from stepfly.utils.config_loader import config


class Memory:
    """
    MongoDB-based global memory for sharing data between multiple agents.
    Supports storing code snippets and data across agent sessions.
    """
    
    _instance = None

    def __init__(self, session_id: str):
        # Load memory database configuration
        memory_config = config.get_section("memory_database")

        # Get database connection info
        host = memory_config.get("host", "localhost")
        port = memory_config.get("port", 27017)

        # Initialize MongoDB connection
        self.client = pymongo.MongoClient(f"mongodb://{host}:{port}/")
        self.db = self.client["tsg_agent_db" + session_id]

        # Collections for different data types
        self.agents_collection = self.db["agents"]
        self.data_collection = self.db["data"]  # Unified data storage
        self.dataframes_collection = self.db["dataframes"]  # Collection for dataframes
        self.code_snippets_collection = self.db["code_snippets"]  # Collection for code snippets

        # Session ID for the current troubleshooting session
        self.session_id = datetime.now().strftime("%Y%m%d_%H%M%S")

        self._initialized = True
        logging.info(f"Memory initialized with MongoDB backend. Session ID: {self.session_id}")

    @classmethod
    def reset_database(cls):
        """Reset the database by dropping all collections"""
        # Load memory database configuration
        memory_config = config.get_section("memory_database")

        # Get database connection info
        host = memory_config.get("host", "localhost")
        port = memory_config.get("port", 27017)

        # Initialize MongoDB connection
        client = pymongo.MongoClient(f"mongodb://{host}:{port}/")
        all_database_names = client.list_database_names()
        for db_name in all_database_names:
            if db_name.startswith("tsg_agent_db"):
                client.drop_database(db_name)
                logging.info(f"Dropped database: {db_name}")
    
    def register_agent(self, agent_name: str, agent_id: Optional[str] = None) -> str:
        if agent_id is None:
            agent_id = str(uuid.uuid4())

        agent_doc = {
            "_id": agent_id,
            "name": agent_name,
            "created_at": datetime.now().isoformat(),
            "conversation_history": [],
            "data_references": []  # References to data items in data_collection
        }
        self.agents_collection.insert_one(agent_doc)
        logging.info(f"Agent registered: {agent_name} with ID {agent_id}")
        return agent_id
    
    def add_agent_context(self, agent_id: str, key: str, value: Any, 
                   description: str = None) -> None:
        # Check if agent exists
        agent = self.agents_collection.find_one({"_id": agent_id})
        if not agent:
            raise ValueError(f"Agent ID {agent_id} not registered")

        timestamp = datetime.now().isoformat()
        context_entry = {
            "key": key,
            "value": value,
            "description": description or "",
            "timestamp": timestamp
        }

        # Add a message to the agent's conversation history
        self.agents_collection.update_one(
            {"_id": agent_id},
            {"$push": {"conversation_history": context_entry}}
        )
        logging.debug(f"Added context for agent {agent_id}: {key}")
    
    def get_agent_context(self, agent_id: str, 
                        limit: int = None, message_only: bool = False) -> List[Dict[str, Any]]:

        # Check if agent exists
        agent = self.agents_collection.find_one({"_id": agent_id})
        if not agent:
            raise ValueError(f"Agent ID {agent_id} not registered")

        history = agent.get("conversation_history", [])

        if message_only:
            # Filter conversation history for only messages and return in simplified format
            messages = [entry["value"] for entry in history
                      if "value" in entry
                      and isinstance(entry["value"], dict)
                      and "role" in entry["value"]
                      and "content" in entry["value"]]

            if limit:
                return messages[-limit:]
            return messages
        else:
            # Return full context entries
            if limit:
                return history[-limit:]
            return history
    
    def add_data(self, data: Any, data_type: str, 
                 agent_id: str = None, metadata: Dict[str, Any] = None,
                 description: str = None) -> str:

        # Handle DataFrame data type using PyMongoArrow
        if isinstance(data, pd.DataFrame):
            return self._add_dataframe(data, data_type, agent_id, metadata, description)

        # For non-DataFrame data
        data_id = str(uuid.uuid4())
        timestamp = datetime.now().isoformat()

        # Create data document
        data_doc = {
            "_id": data_id,
            "data": data,
            "data_type": data_type,
            "timestamp": timestamp,
            "agent_id": agent_id,
            "description": description or "",
            "metadata": metadata or {}
        }

        # For large string data, generate a summary
        if isinstance(data, str) and len(data) > 1000:
            data_doc["summary"] = self._generate_summary(data)

        # Store in MongoDB
        self.data_collection.insert_one(data_doc)

        # Add reference to agent if provided
        if agent_id:
            ref = {
                "data_id": data_id,
                "data_type": data_type,
                "description": description or f"Data of type {data_type}",
                "timestamp": timestamp
            }

            self.agents_collection.update_one(
                {"_id": agent_id},
                {"$push": {"data_references": ref}}
            )

        logging.info(f"Stored data with ID: {data_id}, type: {data_type}")
        return data_id
    
    def _add_dataframe(self, df: pd.DataFrame, data_type: str, 
                      agent_id: str = None, metadata: Dict[str, Any] = None,
                      description: str = None) -> str:
        # Generate unique ID
        data_id = str(uuid.uuid4())
        timestamp = datetime.now().isoformat()
        
        # Create metadata document
        meta_doc = {
            "_id": data_id,
            "data_type": data_type,
            "timestamp": timestamp,
            "agent_id": agent_id,
            "description": description or "",
            "metadata": metadata or {},
            "shape": list(df.shape),
            "columns": list(df.columns),
            "dtypes": {col: str(dtype) for col, dtype in df.dtypes.items()},
            "is_df": True
        }
        
        # Store metadata in MongoDB
        self.data_collection.insert_one(meta_doc)
        
        # Store DataFrame in dataframes collection using PyMongoArrow
        df_with_id = df.copy()
        df_with_id['_memory_id'] = data_id
        df_with_id_to_mongo = df_with_id.reset_index().rename(columns={'index': '_original_index'})
        
        # Use PyMongoArrow to write DataFrame to MongoDB
        write(self.dataframes_collection, df_with_id_to_mongo)
        
        # Add reference to agent if provided
        if agent_id:
            ref = {
                "data_id": data_id,
                "data_type": data_type,
                "description": description or f"DataFrame of type {data_type}",
                "timestamp": timestamp
            }
            
            self.agents_collection.update_one(
                {"_id": agent_id},
                {"$push": {"data_references": ref}}
            )
        
        logging.info(f"Stored DataFrame with ID: {data_id}, type: {data_type}")
        return data_id
    
    def get_data(self, data_id: str) -> Any:
        data_doc = self.data_collection.find_one({"_id": data_id})
        if not data_doc:
            return None

        # Check if this is a DataFrame reference
        is_df = data_doc.get("is_df", False)
        if is_df:
            return self._get_dataframe(data_id)

        return data_doc.get("data")
    
    def _get_dataframe(self, data_id: str) -> pd.DataFrame:
        # Query the dataframe collection
        try:
            # Get DataFrame from MongoDB using PyMongoArrow
            df = find_pandas_all(self.dataframes_collection, {"_memory_id": data_id})
            
            # Check if DataFrame exists
            if df is not None:
                # Remove the _memory_id column
                if '_memory_id' in df.columns:
                    df = df.drop(columns=['_memory_id'])
                if '_id' in df.columns:
                    df = df.drop(columns=['_id'])
                # Set the original index if it exists
                if '_original_index' in df.columns:
                    df = df.set_index('_original_index')
                    df.index.name = None  # Remove name to avoid confusion
                return df
                
            return None
        except Exception as e:
            logging.error(f"Error retrieving DataFrame: {str(e)}")
            return None
    
    def get_data_summary(self, data_id: str) -> str:
        data_doc = self.data_collection.find_one({"_id": data_id})
        if not data_doc:
            return f"Error: Data with ID {data_id} not found"

        # If it's a DataFrame, generate DataFrame summary
        if data_doc.get("is_df", False):
            try:
                df = self._get_dataframe(data_id)
                if df is not None:
                    return self._generate_dataframe_summary(df, data_doc)
                else:
                    return f"Error: DataFrame with ID {data_id} could not be retrieved"
            except Exception as e:
                return f"DataFrame summary error: {str(e)}"

        # Return summary if available, otherwise attempt to create one
        summary = data_doc.get("summary")
        if summary:
            return summary

        data = data_doc.get("data")
        if isinstance(data, str):
            return self._generate_summary(data)

        # For non-string data, return a simple description
        return f"Data of type {data_doc.get('data_type')} (no detailed summary available)"
    
    def _generate_dataframe_summary(self, df: pd.DataFrame, data_doc: Dict[str, Any]) -> str:
        shape = data_doc.get("shape", list(df.shape))
        columns = data_doc.get("columns", list(df.columns))
        
        summary = f"DataFrame shape: {shape}, Columns: {columns}\n\n"
        
        # Add column type information
        summary += "Column data types:\n"
        dtypes = data_doc.get("dtypes", {})
        if dtypes:
            for col, dtype in dtypes.items():
                summary += f"- {col}: {dtype}\n"
        else:
            for col, dtype in df.dtypes.items():
                summary += f"- {col}: {dtype}\n"
        
        # Add first few rows as sample
        num_rows = df.shape[0]
        if num_rows <=3:
            summary += "\nDataFrame has fewer than 4 rows, showing all:\n"
            summary += df.to_string() + "\n"
        else:
            summary += f"\nFirst 2 rows and last 1 rows of DataFrame (total {num_rows} rows):\n"
            summary += df.head(2).to_string() + "\n"
            summary += "...(truncated)...\n"
            summary += df.tail(1).to_string().splitlines()[1] + "\n"
        
        return summary
    
    def get_data_section(self, data_id: str, start_line: int = 0, num_lines: int = 20) -> str:
        data_doc = self.data_collection.find_one({"_id": data_id})
        if not data_doc:
            return f"Error: Data with ID {data_id} not found"

        # If it's a DataFrame, return a slice of the DataFrame
        if data_doc.get("is_df", False):
            try:
                df = self._get_dataframe(data_id)
                if df is not None:
                    total_rows = len(df)
                    if start_line >= total_rows:
                        return f"Error: Start line {start_line} exceeds total rows {total_rows}"

                    end_line = min(start_line + num_lines, total_rows)
                    section = df.iloc[start_line:end_line]

                    return (f"Rows {start_line+1}-{end_line} of {total_rows} from DataFrame {data_id}:\n\n" 
                           f"{section.to_string()}")
                else:
                    return f"Error: DataFrame with ID {data_id} could not be retrieved"
            except Exception as e:
                return f"Error slicing DataFrame: {str(e)}"

        data = data_doc.get("data")
        if not isinstance(data, str):
            return f"Error: Data with ID {data_id} is not text data"

        lines = data.split('\n')
        total_lines = len(lines)

        if start_line >= total_lines:
            return f"Error: Start line {start_line} exceeds total lines {total_lines}"

        end_line = min(start_line + num_lines, total_lines)
        section = '\n'.join(lines[start_line:end_line])

        return (f"Lines {start_line+1}-{end_line} of {total_lines} from data {data_id}:\n\n" 
               f"{section}")
    
    def search_data(self, data_id: str, search_term: str) -> str:
        data_doc = self.data_collection.find_one({"_id": data_id})
        if not data_doc:
            return f"Error: Data with ID {data_id} not found"

        # If it's a DataFrame, search within the DataFrame
        if data_doc.get("is_df", False):
            try:
                df = self._get_dataframe(data_id)
                if df is not None:
                    # Convert all columns to string for searching
                    result_df = None
                    for col in df.columns:
                        try:
                            # Search in this column
                            mask = df[col].astype(str).str.contains(search_term, na=False)
                            if result_df is None:
                                result_df = df[mask]
                            else:
                                result_df = pd.concat([result_df, df[mask]])
                        except:
                            continue

                    if result_df is None or result_df.empty:
                        return f"No matches found for '{search_term}' in DataFrame {data_id}"

                    # Remove duplicates
                    result_df = result_df.drop_duplicates()

                    result = f"Found {len(result_df)} matches for '{search_term}' in DataFrame {data_id}:\n\n"
                    sample_size = min(10, len(result_df))
                    result += result_df.head(sample_size).to_string()

                    if len(result_df) > 10:
                        result += f"\n\n... and {len(result_df) - 10} more matches"

                    return result
                else:
                    return f"Error: DataFrame with ID {data_id} could not be retrieved"
            except Exception as e:
                return f"Error searching DataFrame: {str(e)}"

        data = data_doc.get("data")
        if not isinstance(data, str):
            return f"Error: Data with ID {data_id} is not text data"

        lines = data.split('\n')
        matching_lines = []

        for i, line in enumerate(lines):
            if search_term in line:
                matching_lines.append((i, line.strip()))

        if not matching_lines:
            return f"No matches found for '{search_term}' in data {data_id}"

        result = f"Found {len(matching_lines)} matches for '{search_term}' in data {data_id}:\n\n"
        for i, (line_num, line) in enumerate(matching_lines[:10]):
            result += f"Line {line_num+1}: {line}\n"

        if len(matching_lines) > 10:
            result += f"\n... and {len(matching_lines) - 10} more matches"

        return result
    
    def list_data(self, data_type: str = None, agent_id: str = None) -> str:
        # Build query filter
        query = {}
        if data_type:
            query["data_type"] = data_type
        if agent_id:
            query["agent_id"] = agent_id

        # Find matching data
        data_list = list(self.data_collection.find(query, {
            "_id": 1, "data_type": 1, "timestamp": 1, "description": 1, "is_df": 1
        }))

        if not data_list:
            filter_info = []
            if data_type:
                filter_info.append(f"type '{data_type}'")
            if agent_id:
                filter_info.append(f"agent '{agent_id}'")

            filter_text = f" matching {' and '.join(filter_info)}" if filter_info else ""
            return f"No data{filter_text} found"

        output = f"Found {len(data_list)} data items"
        if data_type:
            output += f" of type '{data_type}'"
        if agent_id:
            output += f" for agent '{agent_id}'"
        output += ":\n\n"

        for item in data_list:
            item_id = item.get("_id", "unknown")
            item_type = item.get("data_type", "unknown")
            timestamp = item.get("timestamp", "unknown")
            description = item.get("description", "")
            is_df = item.get("is_df", False)

            output += f"ID: {item_id}\n"
            output += f"Type: {item_type}\n"
            if is_df:
                output += "Format: DataFrame\n"
            output += f"Time: {timestamp}\n"
            if description:
                output += f"Description: {description}\n"
            output += "\n"

        return output
    
    def store_code_snippet(self, code: str, 
                          plugin_id: str = None,
                          tsg_name: str = None,
                          parameters: Dict[str, Any] = None,
                          description: str = None) -> str:

        snippet_id = str(uuid.uuid4())
        timestamp = datetime.now().isoformat()

        snippet_doc = {
            "_id": snippet_id,
            "code": code,
            "plugin_id": plugin_id,
            "tsg_name": tsg_name,
            "parameters": parameters,
            "description": description or "",
            "timestamp": timestamp
        }
        self.code_snippets_collection.insert_one(snippet_doc)
        logging.info(f"Stored code snippet with ID: {snippet_id}")

        return snippet_id
    
    def get_code_snippet(self, snippet_id: str) -> Optional[str]:
        snippet = self.code_snippets_collection.find_one({"_id": snippet_id})
        if snippet:
            return snippet.get("code")
        return None
    
    def _generate_summary(self, text: Any) -> str:
        # Handle string-type data
        if isinstance(text, str):
            lines = text.split('\n')
            total_lines = len(lines)
            
            # Basic summary
            summary = f"Total lines: {total_lines}, Characters: {len(text)}\n\n"
            
            # Try to detect if this is tabular data
            if '\t' in text or '|' in text or ',' in text:
                delimiter = '\t' if '\t' in text else ('|' if '|' in text else ',')
                
                # Sample some rows to estimate columns
                sample_rows = [line for line in lines[:20] if line.strip()]
                if sample_rows:
                    columns = max(len(row.split(delimiter)) for row in sample_rows)
                    summary += f"Appears to be tabular data with approximately {columns} columns.\n\n"
            
            # Include beginning of the text
            if total_lines > 0:
                sample_size = min(10, total_lines)
                summary += f"First {sample_size} lines:\n" + '\n'.join(lines[:sample_size]) + "\n\n"
            
            # Include end of the text if it's long
            if total_lines > 20:
                summary += f"Last 5 lines:\n" + '\n'.join(lines[-5:])
            
            return summary
        
        # Handle other type data
        return f"Data type: {type(text).__name__}, Summary not available"
    
    def get_data_by_key(self, key: str) -> Any:

        data_doc = self.data_collection.find_one({"metadata.key": key})
        if data_doc:
            # If it's a DataFrame, return the DataFrame
            if data_doc.get("is_df", False):
                return self._get_dataframe(data_doc["_id"])
            return data_doc.get("data")
        return None
    
    def update_data_by_key(self, key: str, data: Any, data_type: str = None, description: str = None) -> str:
        # Find existing data by key
        existing_doc = self.data_collection.find_one({"metadata.key": key})

        if existing_doc:
            # Update existing data
            existing_data_type = existing_doc.get("data_type", data_type or "updated_data")
            existing_description = existing_doc.get("description", description or "Updated data")

            # Remove old data
            self.data_collection.delete_many({"metadata.key": key})

            # Add updated data with same metadata structure
            data_id = self.add_data(
                data=data,
                data_type=data_type or existing_data_type,
                description=description or existing_description,
                metadata={"key": key}
            )

            logging.info(f"Updated data with key: {key}")
            return data_id
        else:
            # Create new data if it doesn't exist
            data_id = self.add_data(
                data=data,
                data_type=data_type or "new_data",
                description=description or f"Data with key: {key}",
                metadata={"key": key}
            )

            logging.info(f"Created new data with key: {key}")
            return data_id

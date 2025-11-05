import os
import re
import json
from typing import List, Dict, Any, Optional

class FileUtils:
    @staticmethod
    def ensure_directory(directory_path: str) -> None:
        """
        Ensure that a directory exists, creating it if necessary
        
        Args:
            directory_path: Path to the directory to ensure
        """
        if not os.path.exists(directory_path):
            os.makedirs(directory_path, exist_ok=True)
    
    @staticmethod
    def read_file(file_path: str) -> str:
        """
        Read the contents of a file
        
        Args:
            file_path: Path to the file to read
            
        Returns:
            The contents of the file
        """
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()
    
    @staticmethod
    def write_file(file_path: str, content: str) -> None:
        """
        Write content to a file
        
        Args:
            file_path: Path to the file to write
            content: Content to write to the file
        """
        FileUtils.ensure_directory(os.path.dirname(file_path))
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)

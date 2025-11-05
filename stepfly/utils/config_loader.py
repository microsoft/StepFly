import os
import json
from typing import Dict, Any, Optional

class ConfigLoader:
    """Helper class to load configuration settings"""
    
    _instance = None
    _config = None
    
    def __new__(cls):
        """Singleton pattern to ensure config is loaded only once"""
        if cls._instance is None:
            cls._instance = super(ConfigLoader, cls).__new__(cls)
            cls._instance._load_config()
        return cls._instance
    
    def _load_config(self) -> None:
        """Load configuration from JSON file"""
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        config_path = os.path.join(project_root, "config", "config.json")

        if os.path.exists(config_path):
            with open(config_path, 'r') as f:
                self._config = json.load(f)
        else:
            print(f"Error loading config")
            self._config = {}
    
    def get(self, key_path: str, default: Any = None) -> Any:
        """
        Get a configuration value by its path
        
        Args:
            key_path: Dot-separated path to configuration value
            default: Default value to return if key is not found
        
        Returns:
            Configuration value or default
        """
        if not self._config:
            return default
            
        parts = key_path.split('.')
        value = self._config
        
        try:
            for part in parts:
                value = value[part]
            return value
        except (KeyError, TypeError):
            return default
            
    def get_section(self, section_path: str) -> Optional[Dict[str, Any]]:
        """
        Get an entire configuration section
        
        Args:
            section_path: Dot-separated path to configuration section
        
        Returns:
            Configuration section as dictionary, or None if not found
        """
        return self.get(section_path, {})

# Create a global instance
config = ConfigLoader() 
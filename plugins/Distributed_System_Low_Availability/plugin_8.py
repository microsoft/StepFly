from plugins.base_plugin import BasePlugin
from datetime import datetime


class DistributedSystemLowAvailabilityPlugin8(BasePlugin):
    """
    Business Scenario and Workflow Analysis
    """
    
    def __init__(self):
        super().__init__(
            plugin_id="plugin_8",
            description=(
                "Generates a SQL query for deployment and configuration analysis. "
                "This plugin will execute the code and store the result in memory."
                "Parameters: "
                "start_time: Start time for analysis window, "
                "end_time: End time for analysis window, "
                "region: Affected region identifier, "
                "environment: Deployment environment (dev/staging/prod), "
            ),
            source_tsg="Distributed_System_Low_Availability",
            language="sql"
        )
        
        self.template = """SELECT 
    correlation_id,
    scenario_name,
    workflow_id,
    workflow_step,
    workflow_status,
    business_criticality,
    total_workflow_time_ms,
    retry_attempts,
    user_id,
    has_compensation,
    timestamp
FROM workflow_tracking
WHERE timestamp >= '{start_time}'
AND timestamp <= '{end_time}'
AND region = '{region}'
AND environment = '{environment}'
AND (is_test_traffic = 0 OR is_test_traffic = false OR is_test_traffic IS NULL)
ORDER BY scenario_name, business_criticality DESC, timestamp
"""
        

    def execute(self, **kwargs) -> str:
        # Validate required parameters
        required_params = ['start_time', 'end_time', 'region', 'environment']
        for param in required_params:
            if param not in kwargs:
                return f"Missing required parameter: {param}. You should provide all the params: {required_params}"
        
        
        # Convert ISO timestamp format to SQLite format
        def convert_timestamp(iso_timestamp):
            if 'T' in iso_timestamp:
                return iso_timestamp.replace('T', ' ').replace('Z', '')
            return iso_timestamp
        
        # Create a copy of kwargs with converted timestamps
        converted_kwargs = kwargs.copy()
        if 'start_time' in converted_kwargs:
            converted_kwargs['start_time'] = convert_timestamp(kwargs['start_time'])
        if 'end_time' in converted_kwargs:
            converted_kwargs['end_time'] = convert_timestamp(kwargs['end_time'])
        
        # Format query with converted parameters
        formatted_query = self.template.format(**converted_kwargs)
        
        return formatted_query

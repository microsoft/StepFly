from plugins.base_plugin import BasePlugin
from datetime import datetime


class DistributedSystemLowAvailabilityPlugin9(BasePlugin):
    """
    Error Pattern and Exception Analysis
    """
    
    def __init__(self):
        super().__init__(
            plugin_id="plugin_9",
            description=(
                "Generates a SQL query for comprehensive availability analysis. "
                "This plugin will execute the code and store the result in memory."
                "Parameters: "
                "start_time: Start time for analysis window, "
                "end_time: End time for analysis window, "
                "region: Affected region identifier, "
                "environment: Deployment environment (dev/staging/prod), "
                "service_name: Name of the affected service, "
            ),
            source_tsg="Distributed_System_Low_Availability",
            language="sql"
        )
        
        self.template = """
WITH error_details AS (
    SELECT 
        error_code,
        error_category,
        exception_type,
        exception_message,
        stack_trace_hash,
        service_component,
        dependency_name,
        COUNT(DISTINCT request_id) as occurrence_count,
        COUNT(DISTINCT user_id) as affected_users,
        COUNT(DISTINCT session_id) as affected_sessions,
        MIN(timestamp) as first_seen,
        MAX(timestamp) as last_seen,
        AVG(latency_ms) as avg_latency_when_error,
        COUNT(DISTINCT strftime('%Y-%m-%d %H:00:00', timestamp)) as hours_affected,
        SUM(CASE WHEN is_retry THEN 1 ELSE 0 END) as retry_attempts,
        SUM(CASE WHEN is_cascading_failure THEN 1 ELSE 0 END) as cascading_failures
    FROM api_gateway_logs
    WHERE timestamp BETWEEN '{start_time}' AND '{end_time}'
    AND region = '{region}'
    AND environment = '{environment}'
    AND service_name = '{service_name}'
    AND status_code >= 500
    AND is_test_traffic = 0
    GROUP BY error_code, error_category, exception_type, exception_message, 
             stack_trace_hash, service_component, dependency_name
),
error_patterns AS (
    SELECT 
        error_category,
        exception_type,
        service_component,
        dependency_name,
        COUNT(DISTINCT stack_trace_hash) as unique_stacktraces,
        SUM(occurrence_count) as total_occurrences,
        SUM(affected_users) as total_affected_users,
        SUM(affected_sessions) as total_affected_sessions,
        MIN(first_seen) as pattern_first_seen,
        MAX(last_seen) as pattern_last_seen,
        AVG(avg_latency_when_error) as avg_error_latency,
        MAX(hours_affected) as max_hours_affected,
        SUM(retry_attempts) as total_retries,
        SUM(cascading_failures) as total_cascading,
        -- Most common error message
        FIRST_VALUE(exception_message) OVER (
            PARTITION BY error_category, exception_type 
            ORDER BY occurrence_count DESC
        ) as most_common_message,
        -- Calculate error velocity (errors per hour)
        SUM(occurrence_count) / NULLIF(
            strftime('%s', (MAX(last_seen) - MIN(first_seen))) / 3600.0, 
            0
        ) as error_velocity
    FROM error_details
    GROUP BY error_category, exception_type, service_component, dependency_name
),
error_impact_analysis AS (
    SELECT 
        error_category,
        exception_type,
        service_component,
        dependency_name,
        unique_stacktraces,
        total_occurrences,
        total_affected_users,
        total_affected_sessions,
        pattern_first_seen,
        pattern_last_seen,
        avg_error_latency,
        total_retries,
        total_cascading,
        most_common_message,
        error_velocity,
        -- Calculate impact score
        (total_occurrences * 0.3 + 
         total_affected_users * 0.4 + 
         total_cascading * 0.2 +
         error_velocity * 0.1) as impact_score,
        -- Determine error pattern
        CASE 
            WHEN error_velocity > 100 THEN 'SPIKE'
            WHEN total_cascading > total_occurrences * 0.1 THEN 'CASCADING'
            WHEN dependency_name IS NOT NULL THEN 'DEPENDENCY'
            WHEN total_retries > total_occurrences * 0.5 THEN 'TRANSIENT'
            ELSE 'PERSISTENT'
        END as error_pattern,
        -- Calculate time since first occurrence
        (strftime('%s', 'now') - strftime('%s', pattern_first_seen)) / 3600.0 as hours_since_start
    FROM error_patterns
),
prioritized_errors AS (
    SELECT 
        *,
        CASE 
            WHEN error_pattern = 'CASCADING' THEN 'CRITICAL'
            WHEN error_pattern = 'SPIKE' AND hours_since_start < 1 THEN 'URGENT'
            WHEN total_affected_users > 1000 THEN 'HIGH'
            WHEN error_pattern = 'DEPENDENCY' THEN 'MEDIUM'
            ELSE 'LOW'
        END as priority,
        ROW_NUMBER() OVER (ORDER BY impact_score DESC) as rank
    FROM error_impact_analysis
)
SELECT 
    error_category,
    exception_type,
    service_component,
    dependency_name,
    total_occurrences,
    total_affected_users,
    error_velocity,
    error_pattern,
    priority,
    most_common_message,
    hours_since_start,
    impact_score,
    rank
FROM prioritized_errors
WHERE rank <= 10
ORDER BY rank
"""
        

    def execute(self, **kwargs) -> str:
        # Validate required parameters
        required_params = ['start_time', 'end_time', 'region', 'environment', 'service_name']
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

from plugins.base_plugin import BasePlugin
from datetime import datetime

class DistributedSystemLowAvailabilityPlugin3(BasePlugin):
    def __init__(self):
        super().__init__(
            plugin_id="plugin_3",
            description=(
                "Generates a SQL query for comprehensive regional and datacenter availability metrics. "
                "This plugin will execute the code and store the result in memory."
                "Parameters: "
                "start_time: Start time for analysis window, "
                "end_time: End time for analysis window, "
                "environment: Deployment environment (dev/staging/prod), "
                "service_name: Name of the affected service, "
            ),
            source_tsg="Distributed_System_Low_Availability",
            language="sql"
        )
        self.template = """
WITH regional_metrics AS (
    SELECT 
        strftime('%Y-%m-%d %H:00:00', timestamp) as hour_bucket,
        region,
        datacenter,
        availability_zone,
        COUNT(DISTINCT request_id) as total_requests,
        COUNT(DISTINCT CASE WHEN status_code BETWEEN 200 AND 299 THEN request_id END) as successful_requests,
        COUNT(DISTINCT CASE WHEN status_code >= 500 THEN request_id END) as failed_requests,
        COUNT(DISTINCT CASE WHEN status_code = 429 THEN request_id END) as rate_limited_requests,
        COUNT(DISTINCT CASE WHEN status_code = 503 THEN request_id END) as unavailable_requests,
        AVG(latency_ms) as avg_latency,
        0 as median_latency,
        0 as p95_latency,
        0 as p99_latency
    FROM api_gateway_logs
    WHERE timestamp BETWEEN '{start_time}' AND '{end_time}'
    AND region = '{region}'
    AND environment = '{environment}'
    AND service_name = '{service_name}'
    AND is_test_traffic = 0
    GROUP BY strftime('%Y-%m-%d %H:00:00', timestamp), region, datacenter, availability_zone
),
regional_availability AS (
    SELECT 
        region,
        datacenter,
        availability_zone,
        SUM(total_requests) as total_count,
        SUM(successful_requests) as success_count,
        SUM(failed_requests) as failure_count,
        SUM(rate_limited_requests) as rate_limited_count,
        SUM(unavailable_requests) as unavailable_count,
        (SUM(successful_requests) * 100.0 / CASE WHEN SUM(total_requests) = 0 THEN NULL ELSE SUM(total_requests) END) as availability_pct,
        AVG(avg_latency) as overall_avg_latency,
        MAX(p99_latency) as max_p99_latency,
        -- Calculate availability trend (simplified for SQLite)
        0 as availability_trend
    FROM regional_metrics
    GROUP BY region, datacenter, availability_zone
)
SELECT 
    region,
    datacenter,
    availability_zone,
    total_count,
    availability_pct,
    failure_count,
    rate_limited_count,
    unavailable_count,
    overall_avg_latency,
    max_p99_latency,
    CASE 
        WHEN availability_trend < -0.01 THEN 'DEGRADING'
        WHEN availability_trend > 0.01 THEN 'IMPROVING'
        ELSE 'STABLE'
    END as trend,
    CASE 
        WHEN availability_pct < 95 THEN 'CRITICAL'
        WHEN availability_pct < 99 THEN 'WARNING'
        ELSE 'HEALTHY'
    END as health_status
FROM regional_availability
WHERE total_count > 100  -- Lowered threshold for demo data
ORDER BY availability_pct ASC, total_count DESC
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

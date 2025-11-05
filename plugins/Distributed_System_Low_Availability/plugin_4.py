from plugins.base_plugin import BasePlugin
from datetime import datetime

class DistributedSystemLowAvailabilityPlugin4(BasePlugin):
    def __init__(self):
        super().__init__(
            plugin_id="plugin_4",
            description=(
                "Generates a SQL query for analyzing availability across logical partitions, shards, and tenant categories. "
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
WITH partition_metrics AS (
    SELECT 
        strftime('%Y-%m-%d %H:' || printf('%02d', (CAST(strftime('%M', timestamp) AS INTEGER) / 30) * 30) || ':00', timestamp) as time_window,
        partition_id,
        shard_id,
        tenant_category,
        COUNT(DISTINCT request_id) as request_count,
        COUNT(DISTINCT CASE WHEN status_code BETWEEN 200 AND 299 THEN request_id END) as success_count,
        COUNT(DISTINCT CASE WHEN status_code >= 500 THEN request_id END) as error_count,
        COUNT(DISTINCT user_id) as unique_users,
        SUM(request_size_bytes) as total_request_bytes,
        SUM(response_size_bytes) as total_response_bytes,
        AVG(latency_ms) as avg_latency,
        0 as latency_stddev,  -- SQLite does not support STDDEV function
        MIN(latency_ms) as min_latency,
        MAX(latency_ms) as max_latency
    FROM api_gateway_logs
    WHERE timestamp BETWEEN '{start_time}' AND '{end_time}'
    AND region = '{region}'
    AND environment = '{environment}'
    AND service_name = '{service_name}'
    AND is_test_traffic = 0
    GROUP BY strftime('%Y-%m-%d %H:' || printf('%02d', (CAST(strftime('%M', timestamp) AS INTEGER) / 30) * 30) || ':00', timestamp), partition_id, shard_id, tenant_category
),
partition_analysis AS (
    SELECT 
        partition_id,
        shard_id,
        tenant_category,
        SUM(request_count) as total_requests,
        SUM(success_count) as total_successes,
        SUM(error_count) as total_errors,
        (SUM(success_count) * 100.0 / CASE WHEN SUM(request_count) = 0 THEN NULL ELSE SUM(request_count) END) as success_rate,
        (SUM(error_count) * 100.0 / CASE WHEN SUM(request_count) = 0 THEN NULL ELSE SUM(request_count) END) as error_rate,
        AVG(avg_latency) as overall_avg_latency,
        AVG(latency_stddev) as avg_latency_variance,
        MAX(max_latency) as worst_latency,
        SUM(unique_users) as affected_users,
        SUM(total_request_bytes) / 1024.0 / 1024.0 as total_request_mb,
        SUM(total_response_bytes) / 1024.0 / 1024.0 as total_response_mb,
        COUNT(DISTINCT time_window) as active_windows
    FROM partition_metrics
    GROUP BY partition_id, shard_id, tenant_category
),
partition_health AS (
    SELECT 
        *,
        -- Calculate health score
        (success_rate * 0.4 + 
         (100 - CASE WHEN error_rate * 2 > 100 THEN 100 ELSE error_rate * 2 END) * 0.3 +
         (CASE WHEN overall_avg_latency < 1000 THEN 100 
               WHEN overall_avg_latency < 3000 THEN 50 
               ELSE 0 END) * 0.3) as health_score,
        -- Identify anomalies
        CASE 
            WHEN error_rate > 10 THEN 'HIGH_ERRORS'
            WHEN overall_avg_latency > 3000 THEN 'HIGH_LATENCY'
            WHEN avg_latency_variance > 1000 THEN 'UNSTABLE'
            WHEN success_rate < 95 THEN 'LOW_SUCCESS'
            ELSE 'HEALTHY'
        END as partition_status
    FROM partition_analysis
    WHERE total_requests > 50  -- Lowered threshold for demo data
)
SELECT 
    partition_id,
    shard_id,
    tenant_category,
    total_requests,
    success_rate,
    error_rate,
    overall_avg_latency,
    worst_latency,
    affected_users,
    health_score,
    partition_status,
    RANK() OVER (ORDER BY health_score ASC) as severity_rank
FROM partition_health
WHERE partition_status != 'HEALTHY'
ORDER BY severity_rank
LIMIT 20
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

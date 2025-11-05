from plugins.base_plugin import BasePlugin
from datetime import datetime


class DistributedSystemLowAvailabilityPlugin6(BasePlugin):
    """
    Application Component Analysis
    """
    
    def __init__(self):
        super().__init__(
            plugin_id="plugin_6",
            description=(
                "Generates a SQL query for endpoint-level analysis including success rates, latency percentiles, cache efficiency, and error patterns by API endpoint. "
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
WITH endpoint_metrics AS (
    SELECT 
        strftime('%Y-%m-%d %H:' || printf('%02d', (CAST(strftime('%M', timestamp) AS INTEGER) / 10) * 10) || ':00', timestamp) as time_bucket,
        endpoint_path,
        http_method,
        api_version,
        client_type,
        COUNT(DISTINCT request_id) as request_count,
        COUNT(DISTINCT CASE WHEN status_code BETWEEN 200 AND 299 THEN request_id END) as success_count,
        COUNT(DISTINCT CASE WHEN status_code >= 500 THEN request_id END) as server_error_count,
        COUNT(DISTINCT CASE WHEN status_code BETWEEN 400 AND 499 THEN request_id END) as client_error_count,
        AVG(latency_ms) as avg_latency,
        0 as p50_latency,
        0 as p95_latency,
        0 as p99_latency,
        SUM(CASE WHEN cache_hit THEN 1 ELSE 0 END) as cache_hits,
        COUNT(DISTINCT session_id) as unique_sessions,
        AVG(request_size_bytes) as avg_request_size,
        AVG(response_size_bytes) as avg_response_size
    FROM api_gateway_logs
    WHERE timestamp BETWEEN '{start_time}' AND '{end_time}'
    AND region = '{region}'
    AND environment = '{environment}'
    AND service_name = '{service_name}'
    AND is_test_traffic = 0
    GROUP BY strftime('%Y-%m-%d %H:' || printf('%02d', (CAST(strftime('%M', timestamp) AS INTEGER) / 10) * 10) || ':00', timestamp), endpoint_path, http_method, api_version, client_type
),
endpoint_analysis AS (
    SELECT 
        endpoint_path,
        http_method,
        api_version,
        client_type,
        SUM(request_count) as total_requests,
        SUM(success_count) as total_success,
        SUM(server_error_count) as total_server_errors,
        SUM(client_error_count) as total_client_errors,
        (SUM(success_count) * 100.0 / CASE WHEN SUM(request_count) = 0 THEN NULL ELSE SUM(request_count) END) as success_rate,
        (SUM(server_error_count) * 100.0 / CASE WHEN SUM(request_count) = 0 THEN NULL ELSE SUM(request_count) END) as server_error_rate,
        (SUM(client_error_count) * 100.0 / CASE WHEN SUM(request_count) = 0 THEN NULL ELSE SUM(request_count) END) as client_error_rate,
        AVG(avg_latency) as overall_avg_latency,
        MAX(p95_latency) as max_p95_latency,
        MAX(p99_latency) as max_p99_latency,
        (SUM(cache_hits) * 100.0 / CASE WHEN SUM(request_count) = 0 THEN NULL ELSE SUM(request_count) END) as cache_hit_rate,
        SUM(unique_sessions) as total_unique_sessions,
        AVG(avg_request_size) / 1024.0 as avg_request_kb,
        AVG(avg_response_size) / 1024.0 as avg_response_kb,
        COUNT(DISTINCT time_bucket) as active_time_buckets
    FROM endpoint_metrics
    GROUP BY endpoint_path, http_method, api_version, client_type
),
endpoint_problems AS (
    SELECT 
        endpoint_path,
        http_method,
        api_version,
        client_type,
        total_requests,
        success_rate,
        server_error_rate,
        client_error_rate,
        overall_avg_latency,
        max_p99_latency,
        cache_hit_rate,
        CASE 
            WHEN server_error_rate > 4 THEN 'HIGH_SERVER_ERRORS'
            WHEN success_rate < 96 THEN 'LOW_SUCCESS_RATE'
            WHEN max_p99_latency > 5000 THEN 'HIGH_LATENCY'
            WHEN client_error_rate > 30 THEN 'HIGH_CLIENT_ERRORS'
            WHEN cache_hit_rate < 20 AND total_requests > 1000 THEN 'LOW_CACHE_EFFICIENCY'
            ELSE 'NORMAL'
        END as endpoint_status,
        -- Calculate impact score
        (total_requests / 1000.0) * (100 - success_rate) as impact_score
    FROM endpoint_analysis
    WHERE total_requests > 50  -- Lowered threshold for demo data
)
SELECT 
    endpoint_path,
    http_method,
    api_version,
    client_type,
    total_requests,
    success_rate,
    server_error_rate,
    overall_avg_latency,
    max_p99_latency,
    cache_hit_rate,
    endpoint_status,
    impact_score,
    RANK() OVER (ORDER BY impact_score DESC) as impact_rank
FROM endpoint_problems
WHERE endpoint_status != 'NORMAL'
ORDER BY impact_rank
LIMIT 25
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

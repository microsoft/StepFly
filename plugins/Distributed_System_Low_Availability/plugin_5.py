from plugins.base_plugin import BasePlugin
from datetime import datetime

class DistributedSystemLowAvailabilityPlugin5(BasePlugin):
    def __init__(self):
        super().__init__(
            plugin_id="plugin_5",
            description=(
                "Generates a SQL query for deep dive into zone-level performance including infrastructure metrics, resource utilization, and connection patterns. "
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
WITH zone_performance AS (
    SELECT 
        strftime('%Y-%m-%d %H:' || printf('%02d', (CAST(strftime('%M', l.timestamp) AS INTEGER) / 15) * 15) || ':00', l.timestamp) as time_interval,
        availability_zone,
        instance_type,
        load_balancer_id,
        COUNT(DISTINCT request_id) as requests,
        COUNT(DISTINCT CASE WHEN status_code BETWEEN 200 AND 299 THEN request_id END) as successful,
        COUNT(DISTINCT CASE WHEN status_code = 504 THEN request_id END) as timeouts,
        COUNT(DISTINCT CASE WHEN status_code = 503 THEN request_id END) as service_unavailable,
        COUNT(DISTINCT CASE WHEN status_code = 502 THEN request_id END) as bad_gateway,
        AVG(latency_ms) as avg_latency,
        AVG(backend_latency_ms) as avg_backend_latency,
        AVG(connection_time_ms) as avg_connection_time,
        MAX(concurrent_connections) as max_connections,
        AVG(im.cpu_utilization) as avg_cpu,
        AVG(im.memory_utilization) as avg_memory
    FROM api_gateway_logs l
    JOIN infrastructure_metrics im ON l.instance_id = im.instance_id 
        AND datetime(l.timestamp) >= datetime(im.timestamp) 
        AND datetime(l.timestamp) < datetime(im.timestamp, '+5 minutes')
    WHERE l.timestamp BETWEEN '{start_time}' AND '{end_time}'
    AND l.region = '{region}'
    AND l.environment = '{environment}'
    AND l.service_name = '{service_name}'
    AND l.is_test_traffic = 0
    GROUP BY strftime('%Y-%m-%d %H:' || printf('%02d', (CAST(strftime('%M', l.timestamp) AS INTEGER) / 15) * 15) || ':00', l.timestamp), availability_zone, instance_type, load_balancer_id
),
zone_aggregates AS (
    SELECT 
        availability_zone,
        instance_type,
        SUM(requests) as total_requests,
        SUM(successful) as total_successful,
        SUM(timeouts) as total_timeouts,
        SUM(service_unavailable) as total_unavailable,
        SUM(bad_gateway) as total_bad_gateway,
        (SUM(successful) * 100.0 / CASE WHEN SUM(requests) = 0 THEN NULL ELSE SUM(requests) END) as success_rate,
        (SUM(timeouts + service_unavailable + bad_gateway) * 100.0 / CASE WHEN SUM(requests) = 0 THEN NULL ELSE SUM(requests) END) as infrastructure_error_rate,
        AVG(avg_latency) as overall_latency,
        AVG(avg_backend_latency) as backend_latency,
        AVG(avg_connection_time) as connection_latency,
        MAX(max_connections) as peak_connections,
        AVG(avg_cpu) as avg_cpu_usage,
        AVG(avg_memory) as avg_memory_usage,
        COUNT(DISTINCT load_balancer_id) as lb_count,
        COUNT(DISTINCT time_interval) as active_intervals
    FROM zone_performance
    GROUP BY availability_zone, instance_type
),
zone_health_assessment AS (
    SELECT 
        *,
        CASE 
            WHEN success_rate < 90 THEN 'CRITICAL'
            WHEN success_rate < 95 THEN 'DEGRADED'
            WHEN infrastructure_error_rate > 5 THEN 'INFRASTRUCTURE_ISSUES'
            WHEN overall_latency > 2000 THEN 'PERFORMANCE_ISSUES'
            WHEN avg_cpu_usage > 80 OR avg_memory_usage > 85 THEN 'RESOURCE_PRESSURE'
            ELSE 'HEALTHY'
        END as zone_status,
        -- Calculate composite health score
        (success_rate * 0.5 + 
         (100 - infrastructure_error_rate) * 0.3 +
         (CASE WHEN overall_latency < 500 THEN 100
               WHEN overall_latency < 1000 THEN 75
               WHEN overall_latency < 2000 THEN 50
               ELSE 25 END) * 0.2) as health_score
    FROM zone_aggregates
    WHERE total_requests > 100  -- Lowered threshold for demo data
)
SELECT 
    availability_zone,
    instance_type,
    total_requests,
    success_rate,
    infrastructure_error_rate,
    overall_latency,
    backend_latency,
    connection_latency,
    peak_connections,
    avg_cpu_usage,
    avg_memory_usage,
    zone_status,
    health_score,
    DENSE_RANK() OVER (ORDER BY health_score ASC) as priority
FROM zone_health_assessment
ORDER BY priority, total_requests DESC
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

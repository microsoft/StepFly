from plugins.base_plugin import BasePlugin
from datetime import datetime

class DistributedSystemLowAvailabilityPlugin1(BasePlugin):
    def __init__(self):
        super().__init__(
            plugin_id="plugin_1",
            description=(
                "Generates a SQL query for service version regression analysis to detect regressions. "
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
WITH version_reliability AS (
    SELECT 
        strftime('%Y-%m-%d %H:%M:00', timestamp) as time_bucket,
        service_version,
        COUNT(DISTINCT request_id) as total_requests,
        COUNT(DISTINCT CASE WHEN status_code >= 500 THEN request_id END) as failed_requests,
        COUNT(DISTINCT CASE WHEN latency_ms > 5000 THEN request_id END) as slow_requests,
        AVG(latency_ms) as avg_latency
    FROM api_gateway_logs
    WHERE timestamp BETWEEN '{start_time}' AND '{end_time}'
    AND region = '{region}'
    AND environment = '{environment}'
    AND service_name = '{service_name}'
    AND is_test_traffic = 0
    GROUP BY strftime('%Y-%m-%d %H:%M:00', timestamp), service_version
),
percentile_calcs AS (
    SELECT
        service_version,
        strftime('%Y-%m-%d %H:%M:00', timestamp) as time_bucket,
        latency_ms,
        ROW_NUMBER() OVER (PARTITION BY service_version, strftime('%Y-%m-%d %H:%M:00', timestamp) ORDER BY latency_ms) as rn,
        COUNT(*) OVER (PARTITION BY service_version, strftime('%Y-%m-%d %H:%M:00', timestamp)) as total_rows
    FROM api_gateway_logs
    WHERE timestamp BETWEEN '{start_time}' AND '{end_time}'
    AND region = '{region}'
    AND environment = '{environment}'
    AND service_name = '{service_name}'
    AND is_test_traffic = 0
),
version_reliability_with_percentiles AS (
    SELECT 
        vr.*,
        COALESCE(MAX(CASE WHEN pc.rn = CAST(pc.total_rows * 0.95 AS INT) THEN pc.latency_ms END), 0) as p95_latency,
        COALESCE(MAX(CASE WHEN pc.rn = CAST(pc.total_rows * 0.99 AS INT) THEN pc.latency_ms END), 0) as p99_latency
    FROM version_reliability vr
    LEFT JOIN percentile_calcs pc ON vr.service_version = pc.service_version AND vr.time_bucket = pc.time_bucket
    GROUP BY vr.time_bucket, vr.service_version, vr.total_requests, vr.failed_requests, vr.slow_requests, vr.avg_latency
),
version_comparison AS (
    SELECT 
        service_version,
        SUM(total_requests) as total_count,
        SUM(failed_requests) as failure_count,
        SUM(slow_requests) as slow_count,
        (SUM(failed_requests) * 100.0 / CASE WHEN SUM(total_requests) = 0 THEN 1 ELSE SUM(total_requests) END) as failure_rate,
        (SUM(slow_requests) * 100.0 / CASE WHEN SUM(total_requests) = 0 THEN 1 ELSE SUM(total_requests) END) as slow_rate,
        AVG(avg_latency) as overall_avg_latency,
        MAX(p99_latency) as max_p99_latency,
        -- Extract version number for comparison (simplified for SQLite)
        CAST(substr(service_version, 1, 
            CASE WHEN instr(service_version, '.') > 0 
                 THEN instr(service_version, '.') - 1 
                 ELSE length(service_version) END) AS INTEGER) as version_major
    FROM version_reliability_with_percentiles
    GROUP BY service_version
),
ranked_versions AS (
    SELECT 
        *,
        ROW_NUMBER() OVER (ORDER BY version_major DESC, service_version DESC) as version_rank,
        LAG(failure_rate) OVER (ORDER BY version_major, service_version) as prev_failure_rate
    FROM version_comparison
    WHERE total_count > 100  -- Lowered threshold for demo data
)
SELECT 
    service_version,
    version_rank,
    total_count,
    ROUND(failure_rate, 2) as failure_rate,
    ROUND(COALESCE(prev_failure_rate, 0), 2) as prev_failure_rate,
    ROUND(failure_rate - COALESCE(prev_failure_rate, 0), 2) as failure_rate_delta,
    ROUND(slow_rate, 2) as slow_rate,
    ROUND(overall_avg_latency, 2) as overall_avg_latency,
    max_p99_latency,
    CASE 
        WHEN version_rank = 1 AND (failure_rate - COALESCE(prev_failure_rate, 0)) > 10 THEN 'REGRESSION_DETECTED'
        WHEN version_rank = 1 AND slow_rate > 10 THEN 'PERFORMANCE_DEGRADATION'
        ELSE 'NO_REGRESSION'
    END as assessment
FROM ranked_versions
ORDER BY version_major DESC, service_version DESC
LIMIT 5
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
        converted_kwargs['start_time'] = convert_timestamp(kwargs['start_time'])
        converted_kwargs['end_time'] = convert_timestamp(kwargs['end_time'])
        
        # Format query with converted parameters
        formatted_query = self.template.format(**converted_kwargs)
        
        return formatted_query

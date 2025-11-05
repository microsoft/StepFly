from plugins.base_plugin import BasePlugin
from datetime import datetime

class DistributedSystemLowAvailabilityPlugin2(BasePlugin):
    def __init__(self):
        super().__init__(
            plugin_id="plugin_2",
            description=(
                "Generates a SQL query to identify feature flags causing reliability issues. "
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
WITH feature_flag_metrics AS (
    SELECT 
        ff.flag_name,
        ff.flag_value,
        COUNT(DISTINCT l.request_id) as request_count,
        COUNT(DISTINCT CASE WHEN l.status_code >= 500 THEN l.request_id END) as error_count,
        COUNT(DISTINCT CASE WHEN l.status_code BETWEEN 200 AND 299 THEN l.request_id END) as success_count,
        AVG(l.latency_ms) as avg_latency,
        MAX(l.latency_ms) as max_latency
    FROM api_gateway_logs l
    JOIN feature_flags ff ON l.request_id = ff.request_id
    WHERE l.timestamp BETWEEN '{start_time}' AND '{end_time}'
    AND l.region = '{region}'
    AND l.environment = '{environment}'
    AND l.service_name = '{service_name}'
    AND l.is_test_traffic = 0
    GROUP BY ff.flag_name, ff.flag_value
),
percentile_data AS (
    SELECT 
        ff.flag_name,
        ff.flag_value,
        l.latency_ms,
        ROW_NUMBER() OVER (PARTITION BY ff.flag_name, ff.flag_value ORDER BY l.latency_ms) as rn,
        COUNT(*) OVER (PARTITION BY ff.flag_name, ff.flag_value) as total_count
    FROM api_gateway_logs l
    JOIN feature_flags ff ON l.request_id = ff.request_id
    WHERE l.timestamp BETWEEN '{start_time}' AND '{end_time}'
    AND l.region = '{region}'
    AND l.environment = '{environment}'
    AND l.service_name = '{service_name}'
    AND l.is_test_traffic = 0
),
flag_metrics_with_percentiles AS (
    SELECT 
        fm.*,
        COALESCE(MAX(CASE WHEN pd.rn = CAST(pd.total_count * 0.95 AS INT) THEN pd.latency_ms END), fm.max_latency) as p95_latency
    FROM feature_flag_metrics fm
    LEFT JOIN percentile_data pd ON fm.flag_name = pd.flag_name AND fm.flag_value = pd.flag_value
    GROUP BY fm.flag_name, fm.flag_value, fm.request_count, fm.error_count, fm.success_count, fm.avg_latency, fm.max_latency
),
flag_analysis AS (
    SELECT 
        flag_name,
        flag_value,
        request_count,
        error_count,
        (error_count * 100.0 / CASE WHEN request_count = 0 THEN 1 ELSE request_count END) as error_rate,
        (success_count * 100.0 / CASE WHEN request_count = 0 THEN 1 ELSE request_count END) as success_rate,
        avg_latency,
        p95_latency,
        max_latency,
        -- Simplified anomaly detection without z-score
        CASE WHEN avg_latency > (SELECT AVG(avg_latency) * 2 FROM flag_metrics_with_percentiles) THEN 1 ELSE 0 END as latency_anomaly
    FROM flag_metrics_with_percentiles
    WHERE request_count > 50  -- Lowered minimum sample size for demo
),
problematic_flags AS (
    SELECT 
        *,
        CASE 
            WHEN error_rate > 8 AND request_count > 1000 THEN 'HIGH_ERROR_RATE'
            WHEN p95_latency > 2000 AND request_count > 50 THEN 'HIGH_LATENCY'
            WHEN latency_anomaly = 1 THEN 'LATENCY_ANOMALY'
            ELSE 'NORMAL'
        END as flag_status,
        ROW_NUMBER() OVER (ORDER BY error_rate DESC, request_count DESC) as severity_rank
    FROM flag_analysis
)
SELECT 
    flag_name,
    flag_value,
    request_count,
    ROUND(error_rate, 2) as error_rate,
    ROUND(success_rate, 2) as success_rate,
    ROUND(avg_latency, 2) as avg_latency,
    p95_latency,
    flag_status,
    severity_rank
FROM problematic_flags
WHERE flag_status != 'NORMAL'
ORDER BY severity_rank
LIMIT 10
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

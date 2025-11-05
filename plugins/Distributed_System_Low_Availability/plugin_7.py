from plugins.base_plugin import BasePlugin
from datetime import datetime


class DistributedSystemLowAvailabilityPlugin7(BasePlugin):
    """
    Product and Customer Segment Analysis
    """
    
    def __init__(self):
        super().__init__(
            plugin_id="plugin_7",
            description=(
                "Generates a SQL query for traffic pattern analysis and load balancing effectiveness. "
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
WITH product_metrics AS (
    SELECT 
        strftime('%Y-%m-%d %H:' || printf('%02d', (CAST(strftime('%M', timestamp) AS INTEGER) / 30) * 30) || ':00', timestamp) as time_window,
        product_id,
        product_category,
        customer_tier,
        subscription_type,
        COUNT(DISTINCT l.request_id) as requests,
        COUNT(DISTINCT CASE WHEN l.status_code BETWEEN 200 AND 299 THEN l.request_id END) as successful,
        COUNT(DISTINCT user_id) as unique_users,
        COUNT(DISTINCT session_id) as unique_sessions,
        SUM(CASE WHEN is_retry THEN 1 ELSE 0 END) as retry_count,
        AVG(latency_ms) as avg_latency,
        MAX(latency_ms) as max_latency,
        SUM(data_processed_bytes) / 1024.0 / 1024.0 as data_processed_mb,
        AVG(CASE WHEN has_dependency_failure THEN 1 ELSE 0 END) * 100 as dependency_failure_pct
    FROM api_gateway_logs l
    JOIN product_metadata pm ON l.request_id = pm.request_id
    WHERE l.timestamp BETWEEN '{start_time}' AND '{end_time}'
    AND l.region = '{region}'
    AND l.environment = '{environment}'
    AND l.service_name = '{service_name}'
    AND l.is_test_traffic = 0
    GROUP BY strftime('%Y-%m-%d %H:' || printf('%02d', (CAST(strftime('%M', timestamp) AS INTEGER) / 30) * 30) || ':00', timestamp), product_id, product_category, 
             customer_tier, subscription_type
),
product_analysis AS (
    SELECT 
        product_id,
        product_category,
        customer_tier,
        subscription_type,
        SUM(requests) as total_requests,
        SUM(successful) as total_successful,
        (SUM(successful) * 100.0 / CASE WHEN SUM(requests) = 0 THEN NULL ELSE SUM(requests) END) as success_rate,
        SUM(unique_users) as affected_users,
        SUM(unique_sessions) as total_sessions,
        (SUM(retry_count) * 100.0 / CASE WHEN SUM(requests) = 0 THEN NULL ELSE SUM(requests) END) as retry_rate,
        AVG(avg_latency) as overall_avg_latency,
        MAX(max_latency) as worst_case_latency,
        SUM(data_processed_mb) as total_data_mb,
        AVG(dependency_failure_pct) as avg_dependency_failures,
        COUNT(DISTINCT time_window) as active_periods
    FROM product_metrics
    GROUP BY product_id, product_category, customer_tier, subscription_type
),
product_health AS (
    SELECT 
        *,
        CASE 
            WHEN customer_tier = 'PREMIUM' AND success_rate < 96 THEN 'SLA_BREACH_PREMIUM'
            WHEN customer_tier = 'STANDARD' AND success_rate < 96.5 THEN 'SLA_BREACH_STANDARD' 
            WHEN success_rate < 94 THEN 'CRITICAL'
            WHEN retry_rate > 20 THEN 'HIGH_RETRY_RATE'
            WHEN avg_dependency_failures > 10 THEN 'DEPENDENCY_ISSUES'
            WHEN overall_avg_latency > 3000 THEN 'PERFORMANCE_DEGRADED'
            ELSE 'HEALTHY'
        END as product_status,
        -- Calculate business impact
        CASE customer_tier
            WHEN 'PREMIUM' THEN affected_users * 10
            WHEN 'STANDARD' THEN affected_users * 3
            ELSE affected_users
        END * (100 - success_rate) / 100 as business_impact_score
    FROM product_analysis
    WHERE total_requests > 10  -- Minimum threshold for meaningful analysis
)
SELECT 
    product_id,
    product_category,
    customer_tier,
    subscription_type,
    total_requests,
    success_rate,
    affected_users,
    retry_rate,
    overall_avg_latency,
    avg_dependency_failures,
    product_status,
    business_impact_score,
    DENSE_RANK() OVER (ORDER BY business_impact_score DESC) as priority
FROM product_health
WHERE product_status != 'HEALTHY'
ORDER BY priority
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

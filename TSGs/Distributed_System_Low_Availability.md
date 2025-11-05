# Distributed System Low Availability Troubleshooting Guide

## Step 1 - Understand the Incident and Collect Parameters

Collect the incident information first and then list out the values for the following parameters from the incident details.

Retrieve the following parameters from the incident detail:
- `region`: The affected region (e.g., `us-east`, `us-west`, `eu-central`)
- `service_name`: The affected service endpoint (e.g., `api.gateway.main`)
- `environment`: The deployment environment (`dev`, `staging`, or `prod`)
- `start_time`: The incident start time minus 2 hours
- `end_time`: The current time or incident resolution time
- `threshold`: The SLA threshold (typically 99.9% for critical services)

**Important**: After collecting parameters, start Steps 2 through 10 in parallel for comprehensive analysis.

## Step 2 - Check Service Version Regression

Execute the following query to analyze if the latest service version has a higher failure rate compared to previous versions.

<PLUGIN_1>
WITH version_reliability AS (
    SELECT 
        DATE_TRUNC('minute', timestamp) as time_bucket,
        service_version,
        COUNT(DISTINCT request_id) as total_requests,
        COUNT(DISTINCT CASE WHEN status_code >= 500 THEN request_id END) as failed_requests,
        COUNT(DISTINCT CASE WHEN latency_ms > 5000 THEN request_id END) as slow_requests,
        AVG(latency_ms) as avg_latency,
        PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY latency_ms) as p95_latency,
        PERCENTILE_CONT(0.99) WITHIN GROUP (ORDER BY latency_ms) as p99_latency
    FROM api_gateway_logs
    WHERE timestamp BETWEEN '{start_time}' AND '{end_time}'
    AND region = '{region}'
    AND environment = '{environment}'
    AND service_name = '{service_name}'
    AND is_test_traffic = 0
    GROUP BY DATE_TRUNC('minute', timestamp), service_version
),
version_comparison AS (
    SELECT 
        service_version,
        SUM(total_requests) as total_count,
        SUM(failed_requests) as failure_count,
        SUM(slow_requests) as slow_count,
        (SUM(failed_requests) * 100.0 / NULLIF(SUM(total_requests), 0)) as failure_rate,
        (SUM(slow_requests) * 100.0 / NULLIF(SUM(total_requests), 0)) as slow_rate,
        AVG(avg_latency) as overall_avg_latency,
        MAX(p99_latency) as max_p99_latency,
        -- Extract version number for comparison
        CAST(SPLIT_PART(service_version, '.', 1) AS INT) * 10000 +
        CAST(SPLIT_PART(service_version, '.', 2) AS INT) * 100 +
        CAST(SPLIT_PART(service_version, '.', 3) AS INT) as version_number
    FROM version_reliability
    GROUP BY service_version
),
ranked_versions AS (
    SELECT 
        *,
        ROW_NUMBER() OVER (ORDER BY version_number DESC) as version_rank,
        LAG(failure_rate) OVER (ORDER BY version_number) as prev_failure_rate,
        failure_rate - LAG(failure_rate) OVER (ORDER BY version_number) as failure_rate_delta
    FROM version_comparison
    WHERE total_count > 1000  -- Minimum traffic for meaningful comparison
)
SELECT 
    service_version,
    version_rank,
    total_count,
    failure_rate,
    prev_failure_rate,
    failure_rate_delta,
    slow_rate,
    overall_avg_latency,
    max_p99_latency,
    CASE 
        WHEN version_rank = 1 AND failure_rate_delta > 10 THEN 'REGRESSION_DETECTED'
        WHEN version_rank = 1 AND slow_rate > 10 THEN 'PERFORMANCE_DEGRADATION'
        ELSE 'NO_REGRESSION'
    END as assessment
FROM ranked_versions
ORDER BY version_number DESC
LIMIT 5
</PLUGIN_1>

If the latest version shows REGRESSION_DETECTED (>10% increase in failure rate), recommend immediate rollback. **This is a potential resolution.**

Otherwise, proceed to Step 11.

## Step 3 - Check Feature Flag Impact

Analyze if any feature flags are causing reliability issues.

<PLUGIN_2>
WITH feature_flag_metrics AS (
    SELECT 
        ff.flag_name,
        ff.flag_value,
        COUNT(DISTINCT l.request_id) as request_count,
        COUNT(DISTINCT CASE WHEN l.status_code >= 500 THEN l.request_id END) as error_count,
        COUNT(DISTINCT CASE WHEN l.status_code BETWEEN 200 AND 299 THEN l.request_id END) as success_count,
        AVG(l.latency_ms) as avg_latency,
        STDDEV(l.latency_ms) as latency_stddev,
        MAX(l.latency_ms) as max_latency,
        PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY l.latency_ms) as p95_latency
    FROM api_gateway_logs l
    JOIN feature_flags ff ON l.request_id = ff.request_id
    WHERE l.timestamp BETWEEN '{start_time}' AND '{end_time}'
    AND l.region = '{region}'
    AND l.environment = '{environment}'
    AND l.service_name = '{service_name}'
    AND l.is_test_traffic = false
    GROUP BY ff.flag_name, ff.flag_value
),
flag_analysis AS (
    SELECT 
        flag_name,
        flag_value,
        request_count,
        error_count,
        (error_count * 100.0 / NULLIF(request_count, 0)) as error_rate,
        (success_count * 100.0 / NULLIF(request_count, 0)) as success_rate,
        avg_latency,
        p95_latency,
        max_latency,
        latency_stddev,
        -- Calculate z-score for anomaly detection
        (avg_latency - AVG(avg_latency) OVER ()) / NULLIF(STDDEV(avg_latency) OVER (), 0) as latency_zscore
    FROM feature_flag_metrics
    WHERE request_count > 100  -- Minimum sample size
),
problematic_flags AS (
    SELECT 
        *,
        CASE 
            WHEN error_rate > 15 AND request_count > 500 THEN 'HIGH_ERROR_RATE'
            WHEN p95_latency > 5000 AND request_count > 500 THEN 'HIGH_LATENCY'
            WHEN latency_zscore > 3 THEN 'LATENCY_ANOMALY'
            ELSE 'NORMAL'
        END as flag_status,
        ROW_NUMBER() OVER (ORDER BY error_rate DESC, request_count DESC) as severity_rank
    FROM flag_analysis
)
SELECT 
    flag_name,
    flag_value,
    request_count,
    error_rate,
    success_rate,
    avg_latency,
    p95_latency,
    flag_status,
    severity_rank
FROM problematic_flags
WHERE flag_status != 'NORMAL'
ORDER BY severity_rank
LIMIT 10
</PLUGIN_2>

If a feature flag shows HIGH_ERROR_RATE (>8% error rate with >1000 requests), recommend disabling it. **This is a potential resolution.**

Otherwise, proceed to Step 11.

## Step 4 - Analyze Regional Availability

Query to see how different regions are affected.

<PLUGIN_3>
WITH regional_metrics AS (
    SELECT 
        DATE_TRUNC('hour', timestamp) as hour_bucket,
        region,
        datacenter,
        availability_zone,
        COUNT(DISTINCT request_id) as total_requests,
        COUNT(DISTINCT CASE WHEN status_code BETWEEN 200 AND 299 THEN request_id END) as successful_requests,
        COUNT(DISTINCT CASE WHEN status_code >= 500 THEN request_id END) as failed_requests,
        COUNT(DISTINCT CASE WHEN status_code = 429 THEN request_id END) as rate_limited_requests,
        COUNT(DISTINCT CASE WHEN status_code = 503 THEN request_id END) as unavailable_requests,
        AVG(latency_ms) as avg_latency,
        PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY latency_ms) as median_latency,
        PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY latency_ms) as p95_latency,
        PERCENTILE_CONT(0.99) WITHIN GROUP (ORDER BY latency_ms) as p99_latency
    FROM api_gateway_logs
    WHERE timestamp BETWEEN '{start_time}' AND '{end_time}'
    AND environment = '{environment}'
    AND service_name = '{service_name}'
    AND is_test_traffic = 0
    GROUP BY DATE_TRUNC('hour', timestamp), region, datacenter, availability_zone
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
        (SUM(successful_requests) * 100.0 / NULLIF(SUM(total_requests), 0)) as availability_pct,
        AVG(avg_latency) as overall_avg_latency,
        MAX(p99_latency) as max_p99_latency,
        -- Calculate availability trend
        CASE 
            WHEN COUNT(DISTINCT hour_bucket) > 1 THEN
                REGR_SLOPE(
                    (successful_requests * 100.0 / NULLIF(total_requests, 0)),
                    EXTRACT(EPOCH FROM hour_bucket)
                )
            ELSE 0
        END as availability_trend
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
WHERE total_count > 1000  -- Meaningful traffic threshold
ORDER BY availability_pct ASC, total_count DESC
</PLUGIN_3>

Identify regions with CRITICAL or WARNING status. Proceed to Step 11.

## Step 5 - Evaluate Partition-Based Availability

Analyze availability across logical partitions (e.g., customer segments, data shards).

<PLUGIN_4>
WITH partition_metrics AS (
    SELECT 
        DATE_TRUNC('30 minutes', timestamp) as time_window,
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
        STDDEV(latency_ms) as latency_stddev,
        MIN(latency_ms) as min_latency,
        MAX(latency_ms) as max_latency
    FROM api_gateway_logs
    WHERE timestamp BETWEEN '{start_time}' AND '{end_time}'
    AND region = '{region}'
    AND environment = '{environment}'
    AND service_name = '{service_name}'
    AND is_test_traffic = 0
    GROUP BY DATE_TRUNC('30 minutes', timestamp), partition_id, shard_id, tenant_category
),
partition_analysis AS (
    SELECT 
        partition_id,
        shard_id,
        tenant_category,
        SUM(request_count) as total_requests,
        SUM(success_count) as total_successes,
        SUM(error_count) as total_errors,
        (SUM(success_count) * 100.0 / NULLIF(SUM(request_count), 0)) as success_rate,
        (SUM(error_count) * 100.0 / NULLIF(SUM(request_count), 0)) as error_rate,
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
         (100 - LEAST(error_rate * 2, 100)) * 0.3 +
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
    WHERE total_requests > 100
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
</PLUGIN_4>

Identify partitions with poor health scores and high severity. Proceed to Step 11.

## Step 6 - Zone-Level Availability Analysis

Analyze availability across availability zones and identify problematic zones.

<PLUGIN_5>
WITH zone_performance AS (
    SELECT 
        DATE_TRUNC('15 minutes', timestamp) as time_interval,
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
        AVG(cpu_utilization) as avg_cpu,
        AVG(memory_utilization) as avg_memory
    FROM api_gateway_logs l
    JOIN infrastructure_metrics im ON l.instance_id = im.instance_id 
        AND l.timestamp = im.timestamp
    WHERE l.timestamp BETWEEN '{start_time}' AND '{end_time}'
    AND l.region = '{region}'
    AND l.environment = '{environment}'
    AND l.service_name = '{service_name}'
    AND l.is_test_traffic = false
    GROUP BY DATE_TRUNC('15 minutes', timestamp), availability_zone, instance_type, load_balancer_id
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
        (SUM(successful) * 100.0 / NULLIF(SUM(requests), 0)) as success_rate,
        (SUM(timeouts + service_unavailable + bad_gateway) * 100.0 / NULLIF(SUM(requests), 0)) as infrastructure_error_rate,
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
    WHERE total_requests > 500
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
</PLUGIN_5>

Zones with CRITICAL or DEGRADED status need immediate attention. Proceed to Step 11.

## Step 7 - Application Component Analysis

Analyze availability by application components and endpoints.

<PLUGIN_6>
WITH endpoint_metrics AS (
    SELECT 
        DATE_TRUNC('10 minutes', timestamp) as time_bucket,
        endpoint_path,
        http_method,
        api_version,
        client_type,
        COUNT(DISTINCT request_id) as request_count,
        COUNT(DISTINCT CASE WHEN status_code BETWEEN 200 AND 299 THEN request_id END) as success_count,
        COUNT(DISTINCT CASE WHEN status_code >= 500 THEN request_id END) as server_error_count,
        COUNT(DISTINCT CASE WHEN status_code BETWEEN 400 AND 499 THEN request_id END) as client_error_count,
        AVG(latency_ms) as avg_latency,
        PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY latency_ms) as p50_latency,
        PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY latency_ms) as p95_latency,
        PERCENTILE_CONT(0.99) WITHIN GROUP (ORDER BY latency_ms) as p99_latency,
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
    GROUP BY DATE_TRUNC('10 minutes', timestamp), endpoint_path, http_method, api_version, client_type
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
        (SUM(success_count) * 100.0 / NULLIF(SUM(request_count), 0)) as success_rate,
        (SUM(server_error_count) * 100.0 / NULLIF(SUM(request_count), 0)) as server_error_rate,
        (SUM(client_error_count) * 100.0 / NULLIF(SUM(request_count), 0)) as client_error_rate,
        AVG(avg_latency) as overall_avg_latency,
        MAX(p95_latency) as max_p95_latency,
        MAX(p99_latency) as max_p99_latency,
        (SUM(cache_hits) * 100.0 / NULLIF(SUM(request_count), 0)) as cache_hit_rate,
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
            WHEN server_error_rate > 10 THEN 'HIGH_SERVER_ERRORS'
            WHEN success_rate < 90 THEN 'LOW_SUCCESS_RATE'
            WHEN max_p99_latency > 5000 THEN 'HIGH_LATENCY'
            WHEN client_error_rate > 30 THEN 'HIGH_CLIENT_ERRORS'
            WHEN cache_hit_rate < 20 AND total_requests > 1000 THEN 'LOW_CACHE_EFFICIENCY'
            ELSE 'NORMAL'
        END as endpoint_status,
        -- Calculate impact score
        (total_requests / 1000.0) * (100 - success_rate) as impact_score
    FROM endpoint_analysis
    WHERE total_requests > 100
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
</PLUGIN_6>

Identify endpoints with HIGH_SERVER_ERRORS or LOW_SUCCESS_RATE. Proceed to Step 11.

## Step 8 - Product/Feature Availability Analysis

Analyze availability by product features and customer segments.

<PLUGIN_7>
WITH product_metrics AS (
    SELECT 
        DATE_TRUNC('30 minutes', timestamp) as time_window,
        product_id,
        product_category,
        customer_tier,
        subscription_type,
        COUNT(DISTINCT request_id) as requests,
        COUNT(DISTINCT CASE WHEN status_code BETWEEN 200 AND 299 THEN request_id END) as successful,
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
    AND l.is_test_traffic = false
    GROUP BY DATE_TRUNC('30 minutes', timestamp), product_id, product_category, 
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
        (SUM(successful) * 100.0 / NULLIF(SUM(requests), 0)) as success_rate,
        SUM(unique_users) as affected_users,
        SUM(unique_sessions) as total_sessions,
        (SUM(retry_count) * 100.0 / NULLIF(SUM(requests), 0)) as retry_rate,
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
            WHEN customer_tier = 'PREMIUM' AND success_rate < 99.5 THEN 'SLA_BREACH_PREMIUM'
            WHEN customer_tier = 'STANDARD' AND success_rate < 99 THEN 'SLA_BREACH_STANDARD'
            WHEN success_rate < 95 THEN 'CRITICAL'
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
    WHERE total_requests > 100
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
</PLUGIN_7>

Products with SLA_BREACH status require immediate action. Proceed to Step 11.

## Step 9 - Scenario/Workflow Analysis

First, execute this query to retrieve raw workflow data and store it in memory:

<PLUGIN_8>
SELECT 
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
</PLUGIN_8>

**Execute plugin_8_tool with the following parameters:**
- `start_time`: From incident parameters
- `end_time`: From incident parameters  
- `region`: From incident parameters (required)
- `environment`: From incident parameters

The raw workflow data is now stored in memory. **Use the code interpreter tool to analyze this data:**

```python
# Access the workflow data from memory and perform comprehensive analysis
# 1. Calculate completion rates by scenario and business criticality
# 2. Identify scenarios with CRITICAL business criticality and poor completion rates
# 3. Analyze workflow steps to find bottlenecks (especially payment_authorization)
# 4. Calculate business impact scores based on affected users and failure rates
# 5. Determine if any CRITICAL scenario has completion rate < 99% (CRITICAL_SCENARIO_FAILING)

# Key analysis points:
# - Group by scenario_name and business_criticality
# - Calculate: completion_rate = (COMPLETED workflows / total workflows) * 100
# - Focus on payment_processing and checkout_flow scenarios
# - Identify failing workflow steps for root cause analysis
# - Generate actionable recommendations

# Decision logic:
# If any CRITICAL scenario has completion_rate < 99%:
#     Status = 'CRITICAL_SCENARIO_FAILING' → Immediate action required
# Else:
#     Continue analysis for other patterns
```

**Based on code interpreter analysis results:**

- If analysis identifies any CRITICAL business scenario with completion rate < 99%, this indicates a confirmed root cause requiring immediate action. **This is a definitive resolution path.**

- Otherwise, the analysis should provide insights on workflow patterns and performance issues to guide further investigation.

The code interpreter analysis will determine the root cause of distributed system availability issues and provide specific remediation steps.

Proceed based on analysis conclusions.

## Step 10 - Top Errors and Exceptions Analysis

Identify the most impactful errors affecting system reliability.

<PLUGIN_9>
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
        COUNT(DISTINCT DATE_TRUNC('hour', timestamp)) as hours_affected,
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
            EXTRACT(EPOCH FROM (MAX(last_seen) - MIN(first_seen))) / 3600.0, 
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
        EXTRACT(EPOCH FROM (NOW() - pattern_first_seen)) / 3600.0 as hours_since_start
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
</PLUGIN_9>

Focus on CRITICAL and URGENT priority errors. Proceed to Step 11.

## Step 11 - Final Analysis and Action Plan

Consolidate findings from all parallel analyses and create an action plan.

Based on the comprehensive analysis from Steps 2-10:

1. **Service Version Issues**: Check if rollback is needed
2. **Feature Flag Problems**: Identify problematic flags to disable
3. **Regional Degradation**: Note affected regions and zones
4. **Partition/Shard Issues**: Identify failing partitions
5. **Application Component Failures**: List critical endpoints
6. **Product/Customer Impact**: Prioritize by business impact
7. **Scenario Failures**: Focus on critical business workflows
8. **Error Patterns**: Address top errors by priority

### Immediate Actions Required:
- If version regression detected → Initiate rollback
- If feature flag issues → Disable problematic flags
- If regional issues → Redirect traffic or scale resources
- If specific errors dominating → Apply targeted fixes

### Communication:
- Update incident channel with findings
- Notify affected product teams
- Escalate to infrastructure team if needed

**This is the final outcome of this TSG.**

<!-- TSG_PLUGINS:Distributed_System_Low_Availability -->

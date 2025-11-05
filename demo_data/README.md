# Demo Data

This directory contains the demo database for StepFly troubleshooting examples.

## Generate Demo Database

The database files (`.db`) are not included in the repository. Run the generation script to create it:

```bash
python demo_data/generate_distributed_system_data.py
```

## What's Inside

The generated `distributed_system.db` contains simulated data for a distributed API gateway system:

- **api_gateway_logs**: Request logs with timestamps, status codes, latencies, service versions, and feature flags
- **feature_flags**: Feature flag assignments per request for A/B testing analysis
- **workflow_tracking**: Business workflow execution traces including payment processing steps
- **service_health_metrics**: System health metrics (CPU, memory, error rates) across regions and zones
- **partition_metrics**: Data partition/shard health and performance metrics
- **component_metrics**: Individual application component performance data
- **product_availability**: Product/feature availability by customer tier

## Hidden Root Cause

The demo data for incident **700000001** has the root cause intentionally hidden in the **workflow_tracking** table. Specifically:

- The `payment_processing` workflow has a ~45% failure rate
- The failure occurs in the `payment_authorization` step  
- This issue only manifests when the new service version combines with the `enhanced_routing_v2` feature flag
- High-value transactions are disproportionately affected
- The root cause is only discoverable in **Step 9 (Scenario/Workflow Analysis)** of the TSG

This realistic scenario demonstrates how StepFly systematically analyzes various system aspects before identifying business-critical workflow failures.


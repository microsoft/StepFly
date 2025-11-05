## Creating Custom TSGs

To create a new troubleshooting guide, follow these steps:

### 1. Create TSG Document

Add your TSG markdown file to the `TSGs/` directory:

```markdown
# Troubleshooting Guide: Database Performance

## Step 1: Check Connection Pool
Query the database to check active connections.

\```sql
SELECT * FROM pg_stat_activity WHERE state = 'active';
\```

## Step 2: Analyze Slow Queries
Use plugin to gather detailed query metrics.

<PLUGIN_1>
SELECT query, total_time, calls 
FROM pg_stat_statements 
WHERE total_time > 1000
ORDER BY total_time DESC;
</PLUGIN_1>

\```python
# Analyze the plugin results
df = memory.get_data("plugin_1_result")
slow_queries = df[df['total_time'] > 1000]
print(slow_queries)
\```
```

### 2. Create Plugin Files (Optional)

If your TSG uses plugins marked as `<PLUGIN_1></PLUGIN_1>`, `<PLUGIN_2></PLUGIN_2>`, etc., create corresponding plugin files in `plugins/YourTSGName/`:

```
plugins/
└── Database_Performance/
    ├── __init__.py
    ├── plugin_1.py
    ├── plugin_2.py
    └── ...
```

Each plugin file should inherit from `BasePlugin` and implement the `execute()` method.

### 3. Create PlanDAG File

Add a corresponding PlanDAG JSON file to `TSGs/PlanDAGs/` defining the workflow structure:

```json
{
    "nodes": [
        {
            "node": "start",
            "description": "Begin troubleshooting",
            "input_edges": [],
            "output_edges": [{"edge": "edge_start_Step1", "condition": "none"}]
        },
        {
            "node": "Step1",
            "description": "Check connection pool",
            "input_edges": [{"edge": "edge_start_Step1"}],
            "output_edges": [{"edge": "edge_Step1_Step2", "condition": "none"}]
        },
        {
            "node": "Step2",
            "description": "Analyze slow queries",
            "input_edges": [{"edge": "edge_Step1_Step2"}],
            "output_edges": [{"edge": "edge_Step2_end", "condition": "none"}]
        },
        {
            "node": "end",
            "description": "End troubleshooting",
            "input_edges": [{"edge": "edge_Step2_end"}],
            "output_edges": []
        }
    ]
}
```

The PlanDAG defines step dependencies, parallel execution paths, and conditional branching based on analysis results.
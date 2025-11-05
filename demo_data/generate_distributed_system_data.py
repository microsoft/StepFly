#!/usr/bin/env python3
"""
Generate demo data for Distributed System Low Availability TSG
The root cause is hidden in workflow/scenario data (Step 9)
"""

import sqlite3
import random
import datetime
from datetime import timedelta
import os

random.seed(42)

class DistributedSystemDataGenerator:
    def __init__(self, db_path="./demo_data/distributed_system.db"):
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.conn = sqlite3.connect(db_path)
        self.cursor = self.conn.cursor()
        self.start_time = datetime.datetime(2024, 1, 20, 6, 30, 0)
        self.end_time = datetime.datetime(2024, 1, 20, 8, 30, 0)
        
    def create_tables(self):
        """Create all necessary tables for the distributed system"""
        
        tables = [
            # Main API gateway logs table
            """CREATE TABLE IF NOT EXISTS api_gateway_logs (
                request_id TEXT PRIMARY KEY,
                timestamp TIMESTAMP,
                region TEXT,
                datacenter TEXT,
                availability_zone TEXT,
                environment TEXT,
                service_name TEXT,
                service_version TEXT,
                endpoint_path TEXT,
                http_method TEXT,
                api_version TEXT,
                client_type TEXT,
                status_code INTEGER,
                latency_ms INTEGER,
                backend_latency_ms INTEGER,
                connection_time_ms INTEGER,
                request_size_bytes INTEGER,
                response_size_bytes INTEGER,
                user_id TEXT,
                session_id TEXT,
                correlation_id TEXT,
                partition_id TEXT,
                shard_id TEXT,
                tenant_category TEXT,
                instance_id TEXT,
                instance_type TEXT,
                load_balancer_id TEXT,
                is_test_traffic BOOLEAN,
                is_retry BOOLEAN,
                cache_hit BOOLEAN,
                has_dependency_failure BOOLEAN,
                error_code TEXT,
                error_category TEXT,
                exception_type TEXT,
                exception_message TEXT,
                stack_trace_hash TEXT,
                service_component TEXT,
                dependency_name TEXT,
                is_cascading_failure BOOLEAN,
                concurrent_connections INTEGER,
                cpu_utilization REAL,
                memory_utilization REAL,
                data_processed_bytes INTEGER
            )""",
            
            # Feature flags table
            """CREATE TABLE IF NOT EXISTS feature_flags (
                request_id TEXT,
                flag_name TEXT,
                flag_value TEXT,
                PRIMARY KEY (request_id, flag_name)
            )""",
            
            # Product metadata table
            """CREATE TABLE IF NOT EXISTS product_metadata (
                request_id TEXT PRIMARY KEY,
                product_id TEXT,
                product_category TEXT,
                customer_tier TEXT,
                subscription_type TEXT
            )""",
            
            # Workflow tracking table - THIS IS WHERE THE ROOT CAUSE IS HIDDEN
            """CREATE TABLE IF NOT EXISTS workflow_tracking (
                correlation_id TEXT PRIMARY KEY,
                timestamp TIMESTAMP,
                scenario_name TEXT,
                workflow_id TEXT,
                workflow_step TEXT,
                workflow_status TEXT,
                business_criticality TEXT,
                total_workflow_time_ms INTEGER,
                retry_attempts INTEGER,
                user_id TEXT,
                region TEXT,
                environment TEXT,
                is_test_traffic BOOLEAN,
                has_compensation BOOLEAN
            )""",
            
            # Infrastructure metrics table
            """CREATE TABLE IF NOT EXISTS infrastructure_metrics (
                instance_id TEXT,
                timestamp TIMESTAMP,
                cpu_utilization REAL,
                memory_utilization REAL,
                disk_utilization REAL,
                network_in_mbps REAL,
                network_out_mbps REAL,
                PRIMARY KEY (instance_id, timestamp)
            )"""
        ]
        
        for table_sql in tables:
            self.cursor.execute(table_sql)
        
        print("Created all tables successfully")
    
    def generate_api_logs(self):
        """Generate main API gateway logs with subtle issues"""
        print("Generating API gateway logs...")
        
        regions = ['us-east', 'us-west', 'eu-central']
        datacenters = ['dc1', 'dc2', 'dc3']
        zones = ['az-1', 'az-2', 'az-3']
        versions = ['3.14.1', '3.14.2']  # New version has issues
        endpoints = [
            '/api/v1/users', '/api/v1/products', '/api/v1/orders',
            '/api/v1/payments', '/api/v1/checkout', '/api/v1/cart',
            '/api/v1/inventory', '/api/v1/shipping', '/api/v1/auth'
        ]
        methods = ['GET', 'POST', 'PUT', 'DELETE']
        client_types = ['web', 'mobile', 'api', 'sdk']
        
        records = []
        current_time = self.start_time
        request_counter = 0
        
        while current_time <= self.end_time:
            # Generate 500-1000 requests per minute
            requests_this_minute = random.randint(500, 1000)
            
            for _ in range(requests_this_minute):
                request_counter += 1
                request_id = f"req_{request_counter:08d}"
                
                # Version distribution - more new version after deployment
                if current_time < self.start_time + timedelta(minutes=30):
                    version = '3.14.1'  # Old version
                else:
                    version = '3.14.2' if random.random() < 0.85 else '3.14.1'
                
                # Base error rate - slightly higher for new version
                if version == '3.14.2':
                    base_error_rate = 0.038  # 3.8% for new version
                else:
                    base_error_rate = 0.032  # 3.2% for old version
                
                # Determine status code
                if random.random() < base_error_rate:
                    status_code = random.choice([500, 502, 503, 504, 429])
                else:
                    status_code = 200
                
                # Latency - slightly worse for new version
                if version == '3.14.2':
                    latency = random.gauss(450, 200) if status_code == 200 else random.gauss(2000, 500)
                else:
                    latency = random.gauss(400, 150) if status_code == 200 else random.gauss(1800, 400)
                
                latency = max(10, int(latency))
                
                record = (
                    request_id,
                    current_time + timedelta(seconds=random.randint(0, 59)),
                    random.choice(regions),
                    random.choice(datacenters),
                    random.choice(zones),
                    'prod',
                    'api.gateway.main',
                    version,
                    random.choice(endpoints),
                    random.choice(methods),
                    'v1',
                    random.choice(client_types),
                    status_code,
                    latency,
                    int(latency * 0.7),  # backend_latency
                    int(latency * 0.1),  # connection_time
                    random.randint(100, 10000),  # request_size
                    random.randint(100, 50000),  # response_size
                    f"user_{random.randint(1, 10000):05d}",
                    f"session_{random.randint(1, 5000):05d}",
                    f"corr_{request_counter:08d}",
                    f"partition_{random.randint(1, 10)}",
                    f"shard_{random.randint(1, 20)}",
                    random.choice(['PREMIUM', 'STANDARD', 'FREE']),
                    f"instance_{random.randint(1, 48)}",
                    random.choice(['t3.large', 't3.xlarge', 'm5.large']),
                    f"lb_{random.randint(1, 12)}",
                    False,  # is_test_traffic
                    random.random() < 0.05,  # is_retry
                    random.random() < 0.3,  # cache_hit
                    status_code >= 500 and random.random() < 0.2,  # has_dependency_failure
                    f"ERR_{status_code}" if status_code >= 500 else None,
                    'SERVER_ERROR' if status_code >= 500 else None,
                    'TimeoutException' if status_code == 504 else 'ServiceException' if status_code >= 500 else None,
                    'Service temporarily unavailable' if status_code == 503 else 'Request timeout' if status_code == 504 else None,
                    f"stack_{random.randint(1, 100)}" if status_code >= 500 else None,
                    random.choice(['auth', 'gateway', 'backend', 'cache']),
                    random.choice(['database', 'redis', 'external_api', None]),
                    status_code >= 500 and random.random() < 0.1,  # is_cascading_failure
                    random.randint(50, 200),  # concurrent_connections
                    random.uniform(50, 85),  # cpu_utilization
                    random.uniform(60, 90),  # memory_utilization
                    random.randint(1000, 100000)  # data_processed_bytes
                )
                records.append(record)
            
            current_time += timedelta(minutes=1)
        
        # Insert records
        self.cursor.executemany("""
            INSERT INTO api_gateway_logs VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
        """, records)
        
        print(f"Generated {len(records)} API gateway log records")
    
    def generate_feature_flags(self):
        """Generate feature flag data - shows some impact but not critical"""
        print("Generating feature flags...")
        
        # Get all request IDs
        self.cursor.execute("SELECT request_id FROM api_gateway_logs")
        request_ids = [row[0] for row in self.cursor.fetchall()]
        
        flags = [
            ('enhanced_routing_v2', ['enabled', 'disabled']),
            ('new_cache_strategy', ['on', 'off']),
            ('experimental_loadbalancer', ['active', 'inactive']),
            ('ab_test_checkout', ['variant_a', 'variant_b', 'control'])
        ]
        
        records = []
        for request_id in request_ids:
            # 50% of requests have enhanced_routing_v2 enabled
            if random.random() < 0.5:
                flag_name = 'enhanced_routing_v2'
                flag_value = 'enabled'
                records.append((request_id, flag_name, flag_value))
                
                # Requests with this flag have slightly higher error rate
                # This is a red herring - not the real cause
                if random.random() < 0.05:
                    self.cursor.execute("""
                        UPDATE api_gateway_logs 
                        SET status_code = 500 
                        WHERE request_id = ? AND status_code = 200 AND random() < 0.02
                    """, (request_id,))
            
            # Add other flags randomly
            for flag_name, flag_values in flags[1:]:
                if random.random() < 0.3:
                    records.append((request_id, flag_name, random.choice(flag_values)))
        
        self.cursor.executemany("INSERT INTO feature_flags VALUES (?, ?, ?)", records)
        print(f"Generated {len(records)} feature flag records")
    
    def generate_workflow_data(self):
        """Generate workflow data - THIS CONTAINS THE ROOT CAUSE"""
        print("Generating workflow tracking data (contains root cause)...")
        
        scenarios = [
            ('user_registration', 'LOW', 0.95),
            ('product_search', 'MEDIUM', 0.97),
            ('add_to_cart', 'MEDIUM', 0.96),
            ('checkout_flow', 'HIGH', 0.88),  # Some issues
            ('payment_processing', 'CRITICAL', 0.55),  # ROOT CAUSE - 45% failure!
            ('order_fulfillment', 'HIGH', 0.92),
            ('inventory_update', 'MEDIUM', 0.94),
            ('shipping_calculation', 'MEDIUM', 0.93),
            ('email_notification', 'LOW', 0.98)
        ]
        
        workflow_steps = {
            'payment_processing': [
                'validate_cart',
                'calculate_total', 
                'apply_discounts',
                'payment_authorization',  # This step is failing!
                'payment_capture',
                'order_confirmation'
            ],
            'checkout_flow': [
                'load_cart',
                'validate_items',
                'shipping_address',
                'payment_method',
                'review_order',
                'place_order'
            ]
        }
        
        records = []
        correlation_counter = 0
        current_time = self.start_time
        
        while current_time <= self.end_time:
            # Generate 100-200 workflows per minute
            workflows_this_minute = random.randint(100, 200)
            
            for _ in range(workflows_this_minute):
                correlation_counter += 1
                correlation_id = f"corr_{correlation_counter:08d}"
                
                scenario_name, criticality, success_rate = random.choices(
                    scenarios,
                    weights=[10, 15, 20, 25, 35, 15, 10, 10, 5],  # More weight on critical scenarios
                    k=1
                )[0]
                
                # Determine workflow status based on scenario
                if random.random() < success_rate:
                    workflow_status = 'COMPLETED'
                    total_time = random.randint(500, 2000)
                else:
                    # Different failure modes
                    if scenario_name == 'payment_processing':
                        # Payment processing fails at authorization step
                        workflow_status = random.choice(['FAILED', 'TIMEOUT'])
                        total_time = random.randint(5000, 15000)  # Takes longer when failing
                    else:
                        workflow_status = random.choice(['FAILED', 'TIMEOUT', 'PARTIAL'])
                        total_time = random.randint(2000, 8000)
                
                # Determine the step (for payment_processing, often fails at authorization)
                if scenario_name in workflow_steps:
                    if workflow_status == 'FAILED' and scenario_name == 'payment_processing':
                        workflow_step = 'payment_authorization'  # ROOT CAUSE LOCATION
                    else:
                        workflow_step = random.choice(workflow_steps[scenario_name])
                else:
                    workflow_step = 'process'
                
                record = (
                    correlation_id,
                    current_time + timedelta(seconds=random.randint(0, 59)),
                    scenario_name,
                    f"wf_{scenario_name}",
                    workflow_step,
                    workflow_status,
                    criticality,
                    total_time,
                    0 if workflow_status == 'COMPLETED' else random.randint(0, 3),  # retry_attempts
                    f"user_{random.randint(1, 10000):05d}",
                    random.choice(['us-east', 'us-west', 'eu-central']),
                    'prod',
                    False,
                    workflow_status == 'FAILED' and random.random() < 0.2  # has_compensation
                )
                records.append(record)
            
            current_time += timedelta(minutes=1)
        
        self.cursor.executemany("""
            INSERT INTO workflow_tracking VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
        """, records)
        
        print(f"Generated {len(records)} workflow tracking records")
        print("ROOT CAUSE: payment_processing workflow has 45% failure rate at payment_authorization step!")
    
    def generate_product_metadata(self):
        """Generate product metadata"""
        print("Generating product metadata...")
        
        # Get all request IDs
        self.cursor.execute("SELECT request_id FROM api_gateway_logs")
        request_ids = [row[0] for row in self.cursor.fetchall()]
        
        products = [f"prod_{i:03d}" for i in range(1, 51)]
        categories = ['electronics', 'clothing', 'books', 'home', 'sports']
        tiers = ['PREMIUM', 'STANDARD', 'FREE']
        subscriptions = ['monthly', 'annual', 'trial', 'one-time']
        
        records = []
        for request_id in request_ids:
            if random.random() < 0.7:  # 70% of requests have product metadata
                record = (
                    request_id,
                    random.choice(products),
                    random.choice(categories),
                    random.choice(tiers),
                    random.choice(subscriptions)
                )
                records.append(record)
        
        self.cursor.executemany("""
            INSERT INTO product_metadata VALUES (?, ?, ?, ?, ?)
        """, records)
        
        print(f"Generated {len(records)} product metadata records")
    
    def generate_infrastructure_metrics(self):
        """Generate infrastructure metrics"""
        print("Generating infrastructure metrics...")
        
        instances = [f"instance_{i}" for i in range(1, 49)]
        
        records = []
        current_time = self.start_time
        
        while current_time <= self.end_time:
            for instance in instances:
                # Normal resource usage - not the root cause
                record = (
                    instance,
                    current_time,
                    random.uniform(55, 75),  # cpu - normal range
                    random.uniform(60, 80),  # memory - normal range
                    random.uniform(40, 60),  # disk
                    random.uniform(100, 300),  # network_in
                    random.uniform(100, 300)   # network_out
                )
                records.append(record)
            
            current_time += timedelta(minutes=5)
        
        self.cursor.executemany("""
            INSERT INTO infrastructure_metrics VALUES (?, ?, ?, ?, ?, ?, ?)
        """, records)
        
        print(f"Generated {len(records)} infrastructure metrics records")
    
    def create_indexes(self):
        """Create indexes for performance"""
        print("Creating indexes...")
        
        indexes = [
            "CREATE INDEX idx_logs_timestamp ON api_gateway_logs(timestamp)",
            "CREATE INDEX idx_logs_region ON api_gateway_logs(region)",
            "CREATE INDEX idx_logs_version ON api_gateway_logs(service_version)",
            "CREATE INDEX idx_logs_status ON api_gateway_logs(status_code)",
            "CREATE INDEX idx_flags_request ON feature_flags(request_id)",
            "CREATE INDEX idx_workflow_scenario ON workflow_tracking(scenario_name)",
            "CREATE INDEX idx_workflow_status ON workflow_tracking(workflow_status)"
        ]
        
        for index_sql in indexes:
            self.cursor.execute(index_sql)
        
        print("Created all indexes")
    
    def run(self):
        """Run all data generation steps"""
        print("Starting distributed system data generation...")
        print("=" * 60)
        
        self.create_tables()
        self.generate_api_logs()
        self.generate_feature_flags()
        self.generate_workflow_data()  # Contains the root cause!
        self.generate_product_metadata()
        self.generate_infrastructure_metrics()
        self.create_indexes()
        
        self.conn.commit()
        
        print("\n" + "=" * 60)
        print("Data generation complete!")
        print("\nSummary:")
        print("- API logs show ~3.8% error rate")
        print("- Feature flags show minor impact")
        print("- Infrastructure metrics are normal")
        print("- Regional distribution is fairly even")
        print("\n*** ROOT CAUSE HIDDEN IN STEP 9 ***")
        print("- payment_processing workflow: 45% failure rate")
        print("- Bottleneck: payment_authorization step")
        print("- Business criticality: CRITICAL")
        print("\nThis will only be discovered during workflow analysis!")
        
        self.conn.close()

if __name__ == "__main__":
    db_path = "./demo_data/distributed_system.db"
    generator = DistributedSystemDataGenerator(db_path)
    generator.run()

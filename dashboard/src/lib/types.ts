export interface HealthStatus {
  status: string;
  timestamp: number;
  engines?: Record<string, string>;
  uptime_seconds?: number;
  version?: string;
}

export interface EngineHealth {
  status: string;
  latency_ms?: number;
  connections?: number;
  operations?: number;
  error?: string;
}

export interface ComplianceAudit {
  framework: string;
  overall_status: string;
  score: number;
  total_controls: number;
  passing: number;
  failing: number;
  partial: number;
  controls: ComplianceControl[];
}

export interface ComplianceControl {
  id: string;
  name: string;
  status: 'pass' | 'fail' | 'partial';
  details: string;
}

export interface ShardingStats {
  is_coordinator: boolean;
  total_shards: number;
  workers: number;
  distributed_tables: string[];
  shard_distribution: Record<string, number>;
}

export interface GridNode {
  node_id: string;
  state: string;
  health_score: number;
  last_heartbeat: string;
  metadata?: Record<string, unknown>;
}

export interface CircuitBreaker {
  name: string;
  state: 'closed' | 'open' | 'half_open';
  failure_count: number;
  last_failure?: string;
  reset_timeout: number;
}

export interface HeartbeatStatus {
  components: Record<string, { status: string; latency_ms: number }>;
  overall: string;
}

export interface MCPTool {
  name: string;
  description: string;
  input_schema: Record<string, unknown>;
}

export interface QueryResponse {
  data: unknown[];
  row_count: number;
  execution_time_ms: number;
  engine_used: string;
  cached: boolean;
}

export interface Customer360 {
  customer_id: string;
  identifiers: Record<string, string>;
  profile: CustomerProfile;
  events: CustomerEvent[];
  relationships: CustomerRelationship[];
}

export interface CustomerProfile {
  rfm_segment?: string;
  health_score?: number;
  churn_risk?: number;
  lifetime_value?: number;
  last_activity?: string;
}

export interface CustomerEvent {
  event_type: string;
  timestamp: string;
  properties: Record<string, unknown>;
}

export interface CustomerRelationship {
  type: string;
  target_id: string;
  target_type: string;
  weight?: number;
}

export interface BenchmarkResult {
  suite: string;
  total_ops: number;
  duration_sec: number;
  ops_per_sec: number;
  avg_latency_ms: number;
  p99_latency_ms: number;
  results: Record<string, unknown>;
}

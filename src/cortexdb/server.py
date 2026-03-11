"""
CortexDB API Server v4.0
Port 5400: CortexQL API  |  Port 5401: Health  |  Port 5402: Admin

Multi-tenant, multi-agent, petabyte-scale sharding, compliance-certified.
Run: uvicorn cortexdb.server:app --host 0.0.0.0 --port 5400
"""

import os
import time
import logging
import secrets
import hashlib
from fastapi import FastAPI, HTTPException, Request, Depends, Header, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Any, Dict, Optional, List
from contextlib import asynccontextmanager

from cortexdb.core.database import CortexDB
from cortexdb.grid import (NodeStateMachine, RepairEngine, GridGarbageCollector,
                            GridHealthScorer, GridCoroner, ResurrectionProtocol)
from cortexdb.heartbeat import HeartbeatProtocol, HealthCheckRunner
from cortexdb.heartbeat.circuit_breaker import CircuitBreakerRegistry
from cortexdb.asa import ASAEnforcer
from cortexdb.tenant.manager import TenantManager, TenantPlan
from cortexdb.tenant.middleware import TenantMiddleware, get_current_tenant
from cortexdb.rate_limit.limiter import RateLimiter
from cortexdb.rate_limit.middleware import RateLimitMiddleware
from cortexdb.observability.metrics import MetricsCollector
from cortexdb.mcp.server import CortexMCPServer
from cortexdb.a2a.registry import A2ARegistry, AgentCard
from cortexdb.a2a.protocol import A2AProtocol
from cortexdb.cortexgraph.identity import IdentityResolver
from cortexdb.cortexgraph.events import EventTracker
from cortexdb.cortexgraph.relationships import RelationshipGraph
from cortexdb.cortexgraph.profiles import BehavioralProfiler
from cortexdb.cortexgraph.insights import CortexGraphInsights
from cortexdb.scale.sharding import CitusShardManager
from cortexdb.scale.replication import ReplicaRouter
from cortexdb.scale.ai_index import AIIndexManager
from cortexdb.scale.rendering import DataRenderer, RenderConfig, RenderFormat
from cortexdb.compliance.framework import ComplianceFramework, Framework
from cortexdb.compliance.encryption import FieldEncryption, KeyManager
from cortexdb.compliance.audit import ComplianceAudit, AuditEventType
from cortexdb.budget.tracker import BudgetTracker
from cortexdb.budget.forecaster import ForecastingAgent
from cortexdb.agents.registry import AgentRegistry, AgentInfo, AgentStatus
from cortexdb.agents.system_metrics import SystemMetricsAgent
from cortexdb.agents.db_monitor import DatabaseMonitorAgent
from cortexdb.agents.service_monitor import ServiceMonitorAgent
from cortexdb.agents.security_agent import SecurityAgent
from cortexdb.agents.error_tracker import ErrorTrackingAgent
from cortexdb.agents.notification_agent import NotificationAgent
from cortexdb.superadmin.auth import SuperAdminAuth
from cortexdb.superadmin.agent_team import AgentTeamManager
from cortexdb.superadmin.ollama_client import OllamaClient
from cortexdb.superadmin.llm_router import LLMRouter
from cortexdb.superadmin.persistence import PersistenceStore
from cortexdb.superadmin.task_executor import TaskExecutor
from cortexdb.superadmin.agent_bus import AgentBus

import json as _json_mod

class _JSONFormatter(logging.Formatter):
    """Structured JSON logging for production observability."""
    def format(self, record):
        log_entry = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info and record.exc_info[0]:
            log_entry["exception"] = self.formatException(record.exc_info)
        if hasattr(record, "request_id"):
            log_entry["request_id"] = record.request_id
        return _json_mod.dumps(log_entry)

_log_format = os.environ.get("LOG_FORMAT", "json")
if _log_format == "json":
    _handler = logging.StreamHandler()
    _handler.setFormatter(_JSONFormatter())
    logging.basicConfig(level=logging.INFO, handlers=[_handler])
else:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")

db: Optional[CortexDB] = None
grid_sm: Optional[NodeStateMachine] = None
repair_eng: Optional[RepairEngine] = None
ggc: Optional[GridGarbageCollector] = None
health_scorer: Optional[GridHealthScorer] = None
coroner: Optional[GridCoroner] = None
resurrection: Optional[ResurrectionProtocol] = None
heartbeat: Optional[HeartbeatProtocol] = None
circuits: Optional[CircuitBreakerRegistry] = None
health_runner: Optional[HealthCheckRunner] = None
asa: Optional[ASAEnforcer] = None
tenant_mgr: Optional[TenantManager] = None
rate_limiter: Optional[RateLimiter] = None
metrics: Optional[MetricsCollector] = None
mcp_server: Optional[CortexMCPServer] = None
a2a_registry: Optional[A2ARegistry] = None
a2a_protocol: Optional[A2AProtocol] = None
identity_resolver: Optional[IdentityResolver] = None
event_tracker: Optional[EventTracker] = None
relationship_graph: Optional[RelationshipGraph] = None
profiler: Optional[BehavioralProfiler] = None
cortexgraph: Optional[CortexGraphInsights] = None
shard_mgr: Optional[CitusShardManager] = None
replica_router: Optional[ReplicaRouter] = None
ai_index: Optional[AIIndexManager] = None
data_renderer: Optional[DataRenderer] = None
compliance: Optional[ComplianceFramework] = None
field_encryption: Optional[FieldEncryption] = None
compliance_audit: Optional[ComplianceAudit] = None
budget_tracker: Optional[BudgetTracker] = None
forecasting_agent: Optional[ForecastingAgent] = None
agent_registry: Optional[AgentRegistry] = None
system_metrics_agent: Optional[SystemMetricsAgent] = None
db_monitor_agent: Optional[DatabaseMonitorAgent] = None
service_monitor_agent: Optional[ServiceMonitorAgent] = None
security_agent: Optional[SecurityAgent] = None
error_tracking_agent: Optional[ErrorTrackingAgent] = None
notification_agent: Optional[NotificationAgent] = None
superadmin_auth: Optional[SuperAdminAuth] = None
agent_team: Optional[AgentTeamManager] = None
ollama_client: Optional[OllamaClient] = None
llm_router: Optional[LLMRouter] = None
persistence_store: Optional[PersistenceStore] = None
task_executor: Optional[TaskExecutor] = None
agent_bus: Optional[AgentBus] = None
secrets_vault = None
agent_memory = None
outcome_analyzer = None
prompt_evolution = None
model_tracker = None
agent_sleep_cycle = None
engine_bridge = None
cost_tracker = None
agent_chat = None
collab_manager = None
llm_rate_limiter = None
agent_tools = None
workflow_engine = None
rag_pipeline = None
template_manager = None
agent_scheduler = None
skill_manager = None
agent_reputation = None
agent_delegation = None
goal_decomposer = None
auto_hiring = None
sprint_planner = None
self_improvement = None
alert_system = None
agent_metrics_mgr = None
execution_replay = None
cost_optimizer = None
compliance_reporter = None
knowledge_graph = None
context_pools = None
knowledge_propagator = None
expert_discovery = None
simulation_engine = None
behavior_tests = None
ab_testing = None
chaos_injector = None
autonomy_loop = None
sentinel = None
_migrator = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global db, grid_sm, repair_eng, ggc, health_scorer
    global coroner, resurrection, heartbeat, circuits, health_runner, asa
    global tenant_mgr, rate_limiter, metrics, mcp_server, a2a_registry, a2a_protocol
    global identity_resolver, event_tracker, relationship_graph, profiler, cortexgraph
    global shard_mgr, replica_router, ai_index, data_renderer
    global compliance, field_encryption, compliance_audit
    global budget_tracker, forecasting_agent
    global agent_registry, system_metrics_agent, db_monitor_agent
    global service_monitor_agent, security_agent, error_tracking_agent, notification_agent
    global superadmin_auth, agent_team, ollama_client, llm_router
    global persistence_store, task_executor, agent_bus, secrets_vault
    global agent_memory, outcome_analyzer, prompt_evolution, model_tracker, agent_sleep_cycle
    global engine_bridge, cost_tracker, agent_chat, collab_manager
    global llm_rate_limiter, agent_tools, workflow_engine, rag_pipeline, template_manager, agent_scheduler
    global skill_manager
    global agent_reputation, agent_delegation, goal_decomposer, auto_hiring
    global sprint_planner, self_improvement, alert_system, agent_metrics_mgr
    global execution_replay, cost_optimizer, compliance_reporter
    global knowledge_graph, context_pools, knowledge_propagator, expert_discovery
    global simulation_engine, behavior_tests, ab_testing, chaos_injector
    global autonomy_loop
    global sentinel

    db = CortexDB()
    await db.connect()

    # Auto-migrate database schema
    global _migrator
    from cortexdb.core.migrator import Migrator
    auto_migrate = os.environ.get("CORTEXDB_AUTO_MIGRATE", "true").lower() in ("true", "1", "yes")
    _migrator = Migrator(db.engines.get("relational").pool, auto_migrate=auto_migrate)
    await _migrator.run()

    # Post-migration compatibility check
    if not await _migrator.check_compatibility():
        current = await _migrator.get_current_version()
        latest = await _migrator.get_latest_version()
        logger.error(
            "Database schema (version %d) is behind migration files (version %d). "
            "Run `python -m cortexdb.migrate up` to apply pending migrations.",
            current, latest,
        )
        if not auto_migrate:
            raise SystemExit(
                f"Database schema is behind (v{current} < v{latest}). "
                f"Run `python -m cortexdb.migrate up` to apply pending migrations."
            )

    # Grid
    grid_sm = NodeStateMachine()
    repair_eng = RepairEngine(grid_sm)
    ggc = GridGarbageCollector(grid_sm)
    health_scorer = GridHealthScorer()
    coroner = GridCoroner()
    resurrection = ResurrectionProtocol(grid_sm)

    # Heartbeat
    heartbeat = HeartbeatProtocol()
    circuits = CircuitBreakerRegistry()
    health_runner = HealthCheckRunner(db.engines)
    asa = ASAEnforcer()

    # Multi-Tenancy
    tenant_mgr = TenantManager(db.engines)

    # Rate Limiting — also bind to app.state for middleware late-binding
    rate_limiter = RateLimiter(db.engines.get("memory"))
    app.state.rate_limiter = rate_limiter

    # Observability
    metrics = MetricsCollector()

    # Setup OTel tracing (optional)
    try:
        from cortexdb.observability.tracing import setup_tracing
        setup_tracing()
    except Exception:
        pass

    # MCP Server
    mcp_server = CortexMCPServer(db)

    # A2A
    a2a_registry = A2ARegistry(db.engines)
    a2a_protocol = A2AProtocol(a2a_registry, db.engines)

    # CortexGraph (DOC-020)
    embedding_pipeline = db.embedding if hasattr(db, 'embedding') else None
    identity_resolver = IdentityResolver(engines=db.engines, embedding=embedding_pipeline)
    relationship_graph = RelationshipGraph(engines=db.engines)
    event_tracker = EventTracker(
        engines=db.engines, identity_resolver=identity_resolver,
        relationship_graph=relationship_graph)
    profiler = BehavioralProfiler(engines=db.engines, embedding=embedding_pipeline)
    cortexgraph = CortexGraphInsights(
        identity_resolver=identity_resolver, event_tracker=event_tracker,
        relationship_graph=relationship_graph, profiler=profiler)

    # Register CortexGraph MCP tools
    mcp_server.register_cortexgraph_tools(cortexgraph)

    # Scale: Sharding, Replication, AI Indexing, Rendering
    shard_mgr = CitusShardManager(db.engines)
    replica_router = ReplicaRouter(db.engines)
    ai_index = AIIndexManager(db.engines)
    data_renderer = DataRenderer(db.engines)

    # Compliance: Framework, Encryption, Audit
    key_manager = KeyManager()
    field_encryption = FieldEncryption(key_manager)
    compliance = ComplianceFramework(db.engines)
    compliance_audit = ComplianceAudit(db.engines)

    # Budget & Forecasting
    budget_tracker = BudgetTracker()
    await budget_tracker.initialize()
    forecasting_agent = ForecastingAgent(budget_tracker)

    # Agents
    agent_registry = AgentRegistry()
    system_metrics_agent = SystemMetricsAgent()
    db_monitor_agent = DatabaseMonitorAgent()
    await db_monitor_agent.initialize()
    service_monitor_agent = ServiceMonitorAgent()
    await service_monitor_agent.initialize()
    security_agent = SecurityAgent()
    await security_agent.initialize()
    error_tracking_agent = ErrorTrackingAgent()
    await error_tracking_agent.initialize()
    notification_agent = NotificationAgent()
    await notification_agent.initialize()

    # Register all agents
    agent_registry.register(AgentInfo(
        agent_id="AGT-SYS-001", title="System Metrics Agent",
        role="Infrastructure Monitor",
        responsibilities=["CPU/memory/disk/network monitoring", "Hardware health tracking", "Performance baselines", "Resource utilization alerts"],
        microservice="cortexdb-server", category="Infrastructure",
    ))
    agent_registry.register(AgentInfo(
        agent_id="AGT-DB-001", title="Database Monitor Agent",
        role="Database Performance Analyst",
        responsibilities=["Connection pool monitoring", "Slow query detection", "Lock analysis", "Replication lag tracking", "Query performance metrics"],
        microservice="postgres / qdrant / redis", category="Database",
    ))
    agent_registry.register(AgentInfo(
        agent_id="AGT-SVC-001", title="Service Monitor Agent",
        role="Microservice Health Manager",
        responsibilities=["Service health checks", "CPU/memory per service", "Request rate monitoring", "Error rate tracking", "Dependency mapping"],
        microservice="all services (12)", category="Infrastructure",
    ))
    agent_registry.register(AgentInfo(
        agent_id="AGT-SEC-001", title="Security Agent",
        role="Threat Detection & Response",
        responsibilities=["Real-time threat detection", "Brute force prevention", "SQL injection blocking", "Audit trail management", "Security posture scoring", "IP blocking"],
        microservice="nginx-gateway / cortexdb-server", category="Security",
    ))
    agent_registry.register(AgentInfo(
        agent_id="AGT-ERR-001", title="Error Tracking Agent",
        role="Error Collection & Analysis",
        responsibilities=["Error aggregation across services", "Stack trace collection", "Error categorization", "Resolution tracking", "Error rate monitoring"],
        microservice="all services", category="Reliability",
    ))
    agent_registry.register(AgentInfo(
        agent_id="AGT-NTF-001", title="Notification Agent",
        role="Event Aggregator & Alerting",
        responsibilities=["Cross-agent event aggregation", "Severity-based prioritization", "Real-time alert delivery", "Notification lifecycle management"],
        microservice="cortexdb-server", category="Operations",
    ))
    agent_registry.register(AgentInfo(
        agent_id="AGT-FRC-001", title="AI Forecasting Agent",
        role="Cost Prediction & Anomaly Detection",
        responsibilities=["Usage trend analysis", "Cost forecasting (monthly/quarterly/annual)", "Anomaly detection via z-score", "Budget breach prediction", "Resource allocation recommendations"],
        microservice="budget-tracker", category="Finance",
    ))

    # Mark all active
    for aid in ["AGT-SYS-001", "AGT-DB-001", "AGT-SVC-001", "AGT-SEC-001", "AGT-ERR-001", "AGT-NTF-001", "AGT-FRC-001"]:
        agent_registry.update_status(aid, AgentStatus.ACTIVE)

    # Initial collection
    system_metrics_agent.collect()

    # SuperAdmin — persistence-backed
    persistence_store = PersistenceStore()
    from cortexdb.superadmin.secrets_vault import SecretsVault
    secrets_vault = SecretsVault(persistence_store._dir)
    secrets_vault.initialize()
    superadmin_auth = SuperAdminAuth()
    ollama_client = OllamaClient()
    from cortexdb.superadmin.model_tracker import ModelPerformanceTracker
    model_tracker = ModelPerformanceTracker(persistence_store)
    llm_router = LLMRouter(ollama_client, model_tracker=model_tracker)
    # Restore encrypted LLM configs from persistence
    for prov in ["ollama", "claude", "openai"]:
        saved = persistence_store.kv_get(f"llm_config:{prov}")
        if saved and secrets_vault and secrets_vault.is_initialized:
            decrypted = secrets_vault.decrypt_dict(saved, ["api_key"])
            llm_router.configure_provider(prov, decrypted)
    agent_team = AgentTeamManager(persistence=persistence_store)
    agent_team.initialize()
    agent_bus = AgentBus()
    agent_bus.set_persistence(persistence_store)
    from cortexdb.superadmin.agent_memory import AgentMemory
    from cortexdb.superadmin.outcome_analyzer import OutcomeAnalyzer
    from cortexdb.superadmin.prompt_evolution import PromptEvolution
    agent_memory = AgentMemory(persistence_store)
    prompt_evolution = PromptEvolution(persistence_store, llm_router)
    outcome_analyzer = OutcomeAnalyzer(llm_router, agent_memory, persistence_store,
                                       prompt_evolution=prompt_evolution)
    async def _on_task_complete(task_id, status):
        await _push_event("task_completed", {"task_id": task_id, "status": status})
    task_executor = TaskExecutor(agent_team, llm_router, memory=agent_memory,
                                 on_complete=_on_task_complete,
                                 outcome_analyzer=outcome_analyzer)

    # Agent Sleep Cycle (Phase 6)
    from cortexdb.superadmin.agent_sleep_cycle import AgentSleepCycle
    agent_sleep_cycle = AgentSleepCycle(
        memory=agent_memory, team=agent_team, analyzer=outcome_analyzer,
        prompt_evo=prompt_evolution, model_tracker=model_tracker,
        persistence=persistence_store,
    )
    import asyncio
    asyncio.create_task(agent_sleep_cycle.start_scheduler(interval_hours=6))

    # Engine Bridge (Phase 7) — connect intelligence to core engines
    from cortexdb.superadmin.engine_bridge import EngineBridge
    engine_bridge = EngineBridge(db.engines)

    # Cost Tracker (Phase 7) — token-precise LLM cost tracking
    from cortexdb.superadmin.cost_tracker import CostTracker
    cost_tracker = CostTracker(persistence_store)

    # Wire cost tracker and engine bridge into task executor
    task_executor._cost_tracker = cost_tracker
    task_executor._engine_bridge = engine_bridge

    # Agent Chat (Phase 7) — direct conversation with agents
    from cortexdb.superadmin.agent_chat import AgentChat
    agent_chat = AgentChat(agent_team, llm_router, agent_memory, cost_tracker)

    # Multi-Agent Collaboration (Phase 7)
    from cortexdb.superadmin.collaboration import CollaborationManager
    collab_manager = CollaborationManager(agent_team, llm_router, agent_memory, persistence_store)

    # Phase 8: LLM Rate Limiter
    from cortexdb.superadmin.llm_rate_limiter import LLMRateLimiter
    llm_rate_limiter = LLMRateLimiter(persistence_store)

    # Phase 8: Agent Tools
    from cortexdb.superadmin.agent_tools import AgentToolSystem
    agent_tools = AgentToolSystem(agent_team, agent_memory, persistence_store)
    agent_chat._tool_system = agent_tools  # wire tools into chat for auto-execution

    # Phase 11: Tool rate limiting
    from cortexdb.superadmin.tool_rate_limiter import ToolRateLimiter
    agent_tools._rate_limiter = ToolRateLimiter()

    # Phase 8: Workflow Engine
    from cortexdb.superadmin.agent_workflows import WorkflowEngine
    workflow_engine = WorkflowEngine(agent_team, llm_router, agent_memory, persistence_store)

    # Phase 8: RAG Pipeline
    from cortexdb.superadmin.rag_pipeline import RAGPipeline
    rag_pipeline = RAGPipeline(engine_bridge, persistence_store)

    # Phase 8: Agent Templates
    from cortexdb.superadmin.agent_templates import AgentTemplateManager
    template_manager = AgentTemplateManager(agent_team, persistence_store)

    # Phase 8: Agent Scheduler
    from cortexdb.superadmin.agent_scheduler import AgentScheduler
    agent_scheduler = AgentScheduler(agent_team, task_executor, persistence_store)
    asyncio.create_task(agent_scheduler.start_scheduler(check_interval=60))

    # Agent Skills — structured skill profiles with levels and auto-enhancement
    from cortexdb.superadmin.agent_skills import AgentSkillManager
    skill_manager = AgentSkillManager(agent_team, persistence_store)

    # Wire skill enhancement into outcome analyzer
    outcome_analyzer._skill_manager = skill_manager

    # Phase 9: Agent Autonomy & Self-Organization
    from cortexdb.superadmin.agent_reputation import AgentReputationManager
    agent_reputation = AgentReputationManager(persistence_store)

    from cortexdb.superadmin.agent_delegation import AgentDelegationEngine
    agent_delegation = AgentDelegationEngine(agent_team, skill_manager, agent_reputation, persistence_store)

    from cortexdb.superadmin.goal_decomposition import GoalDecomposer
    goal_decomposer = GoalDecomposer(agent_team, llm_router, skill_manager, persistence_store)

    from cortexdb.superadmin.auto_hiring import AutoHiringManager
    auto_hiring = AutoHiringManager(agent_team, skill_manager, template_manager, persistence_store)

    from cortexdb.superadmin.sprint_planner import SprintPlanner
    sprint_planner = SprintPlanner(agent_team, llm_router, goal_decomposer, persistence_store)

    from cortexdb.superadmin.self_improvement import SelfImprovementEngine
    self_improvement = SelfImprovementEngine(agent_team, skill_manager, llm_router, persistence_store)

    # Phase 9: Real-Time Operations & Observability
    from cortexdb.superadmin.alert_system import AlertSystem
    alert_system = AlertSystem(persistence_store)

    from cortexdb.superadmin.agent_metrics import AgentMetrics
    agent_metrics_mgr = AgentMetrics(agent_team, skill_manager, agent_reputation, persistence_store)

    from cortexdb.superadmin.execution_replay import ExecutionReplay
    execution_replay = ExecutionReplay(persistence_store)

    from cortexdb.superadmin.cost_optimizer import CostOptimizer
    cost_optimizer = CostOptimizer(llm_router, model_tracker, cost_tracker, persistence_store)

    from cortexdb.superadmin.compliance_reports import ComplianceReporter
    compliance_reporter = ComplianceReporter(agent_team, persistence_store)

    # Phase 10a — Knowledge Network
    from cortexdb.superadmin.knowledge_graph import KnowledgeGraphStore
    knowledge_graph = KnowledgeGraphStore(persistence_store)

    from cortexdb.superadmin.context_pools import SharedContextPools
    context_pools = SharedContextPools(agent_team, persistence_store)

    from cortexdb.superadmin.knowledge_propagator import KnowledgePropagator
    knowledge_propagator = KnowledgePropagator(knowledge_graph, agent_team, skill_manager, persistence_store)

    from cortexdb.superadmin.expert_discovery import ExpertDiscovery
    expert_discovery = ExpertDiscovery(agent_team, skill_manager, knowledge_graph, agent_reputation, persistence_store)

    # Phase 10b — Simulation Sandbox
    from cortexdb.superadmin.simulation_engine import SimulationEngine
    simulation_engine = SimulationEngine(agent_team, persistence_store, llm_router, agent_memory)

    from cortexdb.superadmin.behavior_tests import BehaviorTestManager
    behavior_tests = BehaviorTestManager(simulation_engine, agent_team, llm_router, persistence_store)

    from cortexdb.superadmin.ab_testing import PromptABTesting
    ab_testing = PromptABTesting(simulation_engine, llm_router, persistence_store)

    from cortexdb.superadmin.chaos_injection import ChaosInjector
    chaos_injector = ChaosInjector(simulation_engine, agent_team, llm_router, persistence_store)

    # Phase 11: Autonomy Loop
    from cortexdb.superadmin.autonomy_loop import AutonomyLoop
    autonomy_loop = AutonomyLoop(
        agent_team, llm_router, agent_memory, agent_tools,
        persistence_store, cost_tracker,
    )

    # Phase 12: Marketplace — capability toggle system
    from cortexdb.superadmin.marketplace import MarketplaceManager
    marketplace = MarketplaceManager()

    # Phase 12: Plugin System — custom engine/hook/middleware extensions
    from cortexdb.superadmin.plugin_system import PluginManager
    plugin_manager = PluginManager()

    # Phase 12: AI Copilot
    from cortexdb.superadmin.copilot import CopilotManager
    copilot = CopilotManager(llm_router, agent_team, persistence_store)

    # Phase 12: Agent Template Marketplace
    from cortexdb.superadmin.template_marketplace import TemplateMarketplace
    template_market = TemplateMarketplace(agent_team, persistence_store)

    # Phase 12: GraphQL Gateway
    from cortexdb.superadmin.graphql_gateway import GraphQLGateway
    graphql_gw = GraphQLGateway(db.engines if db else {}, agent_team, persistence_store)

    # Phase 12: Integration — Teams, Discord, Zapier
    from cortexdb.superadmin.teams_integration import TeamsIntegration
    teams_integration = TeamsIntegration(persistence_store, agent_team, agent_bus)

    from cortexdb.superadmin.discord_integration import DiscordIntegration
    discord_integration = DiscordIntegration(persistence_store, agent_team, agent_bus)

    from cortexdb.superadmin.zapier_connector import ZapierConnector
    zapier_connector = ZapierConnector(persistence_store)

    # Phase 12: Voice Interface
    from cortexdb.superadmin.voice_interface import VoiceInterface
    voice_interface = VoiceInterface(llm_router, agent_team, persistence_store)

    # Phase 12: Security — Zero-Trust, Secrets Vault
    from cortexdb.superadmin.zero_trust import ZeroTrustManager
    zero_trust = ZeroTrustManager(persistence_store)

    # Phase 12: Security — Sentinel (Security Testing)
    from cortexdb.sentinel.manager import SentinelManager
    sentinel = SentinelManager(persistence_store, llm_router)

    from cortexdb.superadmin.secrets_vault_v2 import SecretsVaultV2
    secrets_vault_v2 = SecretsVaultV2(persistence_store)

    # Phase 12: Analytics — Pipeline Builder, Custom Dashboards
    from cortexdb.superadmin.pipeline_builder import PipelineBuilder
    pipeline_builder = PipelineBuilder(persistence_store)

    from cortexdb.superadmin.custom_dashboards import CustomDashboardManager
    custom_dashboards = CustomDashboardManager(persistence_store)

    # Phase 12: Infrastructure — Edge, K8s, White-Label, Multi-Region
    from cortexdb.superadmin.edge_deployment import EdgeDeploymentManager
    edge_manager = EdgeDeploymentManager(persistence_store)

    from cortexdb.superadmin.kubernetes_operator import KubernetesOperator
    k8s_operator = KubernetesOperator(persistence_store)

    from cortexdb.superadmin.white_label import WhiteLabelManager
    white_label = WhiteLabelManager(persistence_store)

    from cortexdb.superadmin.multi_region import MultiRegionManager
    multi_region = MultiRegionManager(persistence_store)

    # Wire alert system and reputation into outcome analyzer
    outcome_analyzer._alert_system = alert_system
    outcome_analyzer._reputation = agent_reputation

    # Wire execution replay into task executor
    task_executor._execution_replay = execution_replay

    # Register CDB team agents in the unified registry
    for cdb_agent in agent_team.get_all_agents():
        aid = cdb_agent["agent_id"]
        if aid not in [a["agent_id"] for a in agent_registry.get_all_agents()]:
            agent_registry.register(AgentInfo(
                agent_id=aid,
                title=cdb_agent["name"],
                role=cdb_agent["title"],
                responsibilities=cdb_agent.get("responsibilities", []),
                microservice="superadmin",
                category=cdb_agent.get("department", "EXEC"),
            ))
            agent_registry.update_status(aid, AgentStatus.ACTIVE)

    # Start background task executor
    asyncio.create_task(task_executor.start())
    asyncio.create_task(persistence_store.start_auto_save())

    await ggc.start()
    yield

    # ── Graceful shutdown with timeouts ──
    logger.info("CortexDB shutting down...")

    # Stop superadmin background services
    if task_executor:
        task_executor.stop()
    if persistence_store:
        persistence_store.stop()
        logger.info("SuperAdmin state persisted to disk")

    # 1. Drain pending async writes (30s max)
    if db and db.write_fanout:
        try:
            await asyncio.wait_for(db.write_fanout.drain(timeout=25), timeout=30)
            logger.info(f"Async writes drained. DLQ size: {len(db.write_fanout.dlq)}")
        except asyncio.TimeoutError:
            logger.warning("Write drain timeout — some async writes may be lost")

    # 2. Stop GGC (10s max)
    try:
        await asyncio.wait_for(ggc.stop(), timeout=10)
    except asyncio.TimeoutError:
        logger.warning("GGC shutdown timeout — forcing")

    # 3. Close database connections (10s max)
    try:
        await asyncio.wait_for(db.close(), timeout=10)
    except asyncio.TimeoutError:
        logger.warning("Database close timeout — connections may leak")

    logger.info("CortexDB shutdown complete")


from cortexdb import __version__
_is_production = os.environ.get("CORTEX_ENV", "development") == "production"
app = FastAPI(
    title="CortexDB",
    description="Consciousness-Inspired Unified Database — replaces PostgreSQL + Redis + Pinecone + Neo4j + TimescaleDB + Kafka + Hyperledger with one system.",
    version=__version__,
    lifespan=lifespan,
    docs_url=None if _is_production else "/docs",
    redoc_url=None if _is_production else "/redoc",
    openapi_url=None if _is_production else "/openapi.json",
    contact={"name": "Nirlab Inc", "url": "https://nirlab.ai", "email": "support@nirlab.ai"},
    license_info={"name": "Proprietary", "url": "https://nirlab.ai/license"},
    terms_of_service="https://nirlab.ai/terms",
)
_cors_origins = os.environ.get("CORTEX_CORS_ORIGINS", "http://localhost:3000,http://localhost:5400").split(",")
app.add_middleware(CORSMiddleware, allow_origins=_cors_origins,
                   allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
                   allow_headers=["Authorization", "Content-Type", "X-Tenant-Key", "X-Request-ID"])
app.add_middleware(RateLimitMiddleware, rate_limiter=None)  # Wired in lifespan via app.state
app.add_middleware(TenantMiddleware, tenant_manager=None)    # Wired in lifespan via app.state


# -- Global Exception Handler --

from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi.exceptions import RequestValidationError

@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": True, "status": exc.status_code, "message": str(exc.detail),
                 "request_id": getattr(request.state, "request_id", None)},
    )

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={"error": True, "status": 422, "message": "Validation error",
                 "details": exc.errors(),
                 "request_id": getattr(request.state, "request_id", None)},
    )

@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.error("Unhandled exception on %s %s: %s", request.method, request.url.path, exc, exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"error": True, "status": 500, "message": "Internal server error",
                 "request_id": getattr(request.state, "request_id", None)},
    )


# -- API Version & Request ID Middleware --

import uuid as _uuid_mod

@app.middleware("http")
async def add_headers_middleware(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID", str(_uuid_mod.uuid4()))
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    response.headers["X-API-Version"] = __version__
    response.headers["X-Powered-By"] = "CortexDB"
    return response


# -- Health Endpoint Auth --

_metrics_token = os.environ.get("CORTEX_METRICS_TOKEN", "")

def _check_metrics_auth(request: Request):
    """Protect sensitive health endpoints with bearer token in production."""
    if not _is_production or not _metrics_token:
        return True
    auth = request.headers.get("Authorization", "")
    return auth == f"Bearer {_metrics_token}"


def _tenant_id(request: Request) -> Optional[str]:
    return getattr(request.state, "tenant_id", None)


# -- Models --

class QueryRequest(BaseModel):
    cortexql: str
    params: Optional[Dict] = None
    hint: Optional[str] = None

class WriteRequest(BaseModel):
    data_type: str
    payload: Dict
    actor: str = "api"

class QueryResponse(BaseModel):
    data: Any = None
    tier_served: str = "R3"
    engines_hit: List[str] = []
    latency_ms: float = 0
    cache_hit: bool = False
    metadata: Dict = {}

class TenantOnboardRequest(BaseModel):
    tenant_id: str
    name: str
    plan: str = "free"
    config: Optional[Dict] = None

class AgentCardRequest(BaseModel):
    agent_id: str
    name: str
    description: str
    skills: List[str] = []
    tools: List[str] = []
    endpoint_url: str = ""
    protocol: str = "mcp"
    model: str = ""

class A2ATaskRequest(BaseModel):
    source_agent_id: str
    target_agent_id: str
    skill: str
    input_data: Dict = {}
    priority: int = 3

class IdentifyRequest(BaseModel):
    identifiers: Dict[str, str]
    attributes: Optional[Dict] = None

class TrackEventRequest(BaseModel):
    customer_id: str
    event_type: str
    properties: Optional[Dict] = None
    source: str = "api"
    session_id: str = ""
    channel: str = ""

class TrackBatchRequest(BaseModel):
    events: List[Dict]

class MergeCustomersRequest(BaseModel):
    canonical_id: str
    duplicate_id: str
    reason: str = "manual"

class MCPToolCallRequest(BaseModel):
    tool: str
    input: Dict = {}


# -- Core Endpoints --

@app.post("/v1/query", response_model=QueryResponse)
async def cortexql_query(req: QueryRequest, request: Request):
    tid = _tenant_id(request)
    result = await db.query(req.cortexql, req.params, req.hint, tenant_id=tid)
    if metrics:
        metrics.record_query(result.tier_served.value, result.latency_ms, result.cache_hit, tid)
    # Return 403 if blocked by Amygdala
    if isinstance(result.data, dict) and result.data.get("error") == "BLOCKED_BY_AMYGDALA":
        raise HTTPException(403, detail={
            "error": "blocked_by_amygdala",
            "threats": result.data.get("threats", []),
        })
    return QueryResponse(data=result.data, tier_served=result.tier_served.value,
                         engines_hit=result.engines_hit, latency_ms=round(result.latency_ms, 3),
                         cache_hit=result.cache_hit, metadata=result.metadata)

@app.post("/v1/write")
async def cortexql_write(req: WriteRequest, request: Request):
    tid = _tenant_id(request)
    result = await db.write(req.data_type, req.payload, req.actor, tenant_id=tid)
    if metrics:
        metrics.record_write(req.data_type, result.get("latency_ms", 0),
                             len(result.get("sync", {})), len(result.get("async", {})))
    return {"status": "success", "fan_out": result}


# -- Health Endpoints (DOC-014 + DOC-019) --

@app.get("/health/live")
async def health_live():
    return {"status": "alive", "timestamp": time.time()}

@app.get("/health/ready")
async def health_ready():
    if not db or not db._connected:
        raise HTTPException(503, "CortexDB not ready")
    result = await health_runner.check_readiness()
    if not result.is_healthy:
        raise HTTPException(503, result.errors)
    return {"status": result.status, "engines": result.checks}

@app.get("/health/deep")
async def health_deep(request: Request):
    if not _check_metrics_auth(request):
        raise HTTPException(401, "Authorization required for deep health endpoint")
    if not db:
        raise HTTPException(503, "CortexDB not initialized")
    db_health = await db.health()
    deep = await health_runner.check_deep_health()
    db_health["deep_health"] = {"status": deep.status, "warnings": deep.warnings, "errors": deep.errors}
    db_health["grid"] = {"active_nodes": grid_sm.topology_size if grid_sm else 0,
                         "ggc_stats": ggc.get_stats() if ggc else {}}
    db_health["tenants"] = tenant_mgr.get_stats() if tenant_mgr else {}
    db_health["a2a"] = a2a_registry.get_stats() if a2a_registry else {}
    db_health["rate_limiter"] = rate_limiter.get_stats() if rate_limiter else {}
    db_health["cortexgraph"] = cortexgraph.get_stats() if cortexgraph else {}
    db_health["sharding"] = shard_mgr.get_stats() if shard_mgr else {}
    db_health["replicas"] = replica_router.get_stats() if replica_router else {}
    db_health["ai_index"] = ai_index.get_stats() if ai_index else {}
    db_health["rendering"] = data_renderer.get_stats() if data_renderer else {}
    db_health["compliance"] = compliance.get_stats() if compliance else {}
    db_health["encryption"] = field_encryption.get_stats() if field_encryption else {}
    db_health["audit_trail"] = compliance_audit.get_stats() if compliance_audit else {}
    return db_health

@app.get("/health/metrics")
async def health_metrics(request: Request):
    """Prometheus-compatible metrics endpoint."""
    if not _check_metrics_auth(request):
        raise HTTPException(401, "Authorization required for metrics endpoint")
    if not metrics:
        return "# No metrics available\n"
    from fastapi.responses import PlainTextResponse
    return PlainTextResponse(metrics.export_prometheus(), media_type="text/plain")


# -- Admin Auth Guard --

def _verify_admin(request: Request):
    """Verify admin token for /admin/* and /v1/admin/* endpoints."""
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    if not token:
        token = request.headers.get("X-Admin-Token", "")
    import secrets as _secrets
    expected = os.environ.get("CORTEX_ADMIN_TOKEN", "")
    if not expected or not _secrets.compare_digest(token, expected):
        raise HTTPException(401, "Admin authentication required")


# -- Admin Endpoints (all require admin token) --

@app.get("/admin/cache/stats")
async def cache_stats(request: Request):
    _verify_admin(request)
    return db.read_cascade.stats if db and db.read_cascade else {}

@app.get("/admin/plasticity/top-paths")
async def top_paths(request: Request):
    _verify_admin(request)
    return db.plasticity.top_paths if db else []

@app.get("/admin/engines")
async def engine_list(request: Request):
    _verify_admin(request)
    if not db: return {"engines": {}}
    result = {}
    for name, engine in db.engines.items():
        try: result[name] = await engine.health()
        except Exception as e: result[name] = {"status": "error", "error": str(e)}
    return {"engines": result}

@app.post("/admin/plasticity/decay")
async def trigger_decay(request: Request):
    _verify_admin(request)
    if db: db.plasticity.decay()
    return {"status": "decay_triggered"}

@app.post("/admin/ledger/verify")
async def verify_ledger(request: Request):
    _verify_admin(request)
    if "immutable" in db.engines:
        intact = await db.engines["immutable"].verify_chain()
        return {"chain_intact": intact, "entries": len(db.engines["immutable"]._chain)}
    return {"error": "ImmutableCore not connected"}

@app.post("/admin/sleep-cycle/run")
async def run_sleep_cycle(request: Request):
    _verify_admin(request)
    if agent_sleep_cycle:
        result = await agent_sleep_cycle.run()
        return result
    return {"error": "Sleep cycle not available"}

@app.get("/admin/sleep-cycle/status")
async def sleep_cycle_status(request: Request):
    _verify_admin(request)
    return agent_sleep_cycle.get_status() if agent_sleep_cycle else {}


# -- Tenant Endpoints (DOC-019 Section 6, admin-protected) --

@app.post("/v1/admin/tenants")
async def tenant_onboard(req: TenantOnboardRequest, request: Request):
    _verify_admin(request)
    plan = TenantPlan(req.plan) if req.plan in [p.value for p in TenantPlan] else TenantPlan.FREE
    result = await tenant_mgr.onboard(req.tenant_id, req.name, plan, req.config)
    return result

@app.get("/v1/admin/tenants")
async def tenant_list(request: Request, status: Optional[str] = None):
    _verify_admin(request)
    return {"tenants": tenant_mgr.list_tenants(status) if tenant_mgr else []}

@app.get("/v1/admin/tenants/{tenant_id}")
async def tenant_get(tenant_id: str, request: Request):
    _verify_admin(request)
    tenant = tenant_mgr.get_tenant(tenant_id) if tenant_mgr else None
    if not tenant:
        raise HTTPException(404, "Tenant not found")
    return {"tenant_id": tenant.tenant_id, "name": tenant.name,
            "plan": tenant.plan.value, "status": tenant.status.value,
            "rate_limits": tenant.effective_rate_limits}

@app.post("/v1/admin/tenants/{tenant_id}/activate")
async def tenant_activate(tenant_id: str, request: Request):
    _verify_admin(request)
    await tenant_mgr.activate(tenant_id)
    return {"status": "activated"}

@app.post("/v1/admin/tenants/{tenant_id}/suspend")
async def tenant_suspend(tenant_id: str, request: Request, reason: str = ""):
    _verify_admin(request)
    await tenant_mgr.suspend(tenant_id, reason)
    return {"status": "suspended"}

@app.post("/v1/admin/tenants/{tenant_id}/deactivate")
async def tenant_deactivate(tenant_id: str, request: Request):
    _verify_admin(request)
    await tenant_mgr.deactivate(tenant_id)
    return {"status": "offboarding"}

@app.post("/v1/admin/tenants/{tenant_id}/export")
async def tenant_export(tenant_id: str, request: Request):
    _verify_admin(request)
    return await tenant_mgr.export_data(tenant_id)

@app.post("/v1/admin/tenants/{tenant_id}/purge")
async def tenant_purge(tenant_id: str, request: Request):
    _verify_admin(request)
    return await tenant_mgr.purge(tenant_id)

@app.get("/v1/admin/tenants/{tenant_id}/isolation")
async def tenant_isolation_report(tenant_id: str, request: Request):
    _verify_admin(request)
    if db and db.tenant_isolation:
        return await db.tenant_isolation.isolation_report(tenant_id)
    return {"error": "Tenant isolation not initialized"}


# -- Convenience Endpoints --

@app.get("/v1/blocks")
async def list_blocks(request: Request, block_type: Optional[str] = None, limit: int = 50):
    limit = max(1, min(limit, 500))  # Bound limit
    params = []
    query = "SELECT * FROM blocks WHERE status = 'active'"
    if block_type:
        if not block_type.isalnum() and not all(c.isalnum() or c in '-_' for c in block_type):
            raise HTTPException(400, "Invalid block_type format")
        params.append(block_type)
        query += f" AND block_type = ${len(params)}"
    params.append(limit)
    query += f" ORDER BY usage_count DESC LIMIT ${len(params)}"
    result = await db.query(query, tenant_id=_tenant_id(request), params=params)
    return {"blocks": result.data, "tier": result.tier_served.value}

@app.get("/v1/agents")
async def list_agents(request: Request, state: Optional[str] = None, limit: int = 50):
    limit = max(1, min(limit, 500))  # Bound limit
    params = []
    query = "SELECT * FROM agents"
    if state:
        VALID_STATES = {"idle", "running", "paused", "stopped", "error", "active"}
        if state not in VALID_STATES:
            raise HTTPException(400, f"Invalid state. Must be one of: {VALID_STATES}")
        params.append(state)
        query += f" WHERE state = ${len(params)}"
    params.append(limit)
    query += f" ORDER BY created_at DESC LIMIT ${len(params)}"
    result = await db.query(query, tenant_id=_tenant_id(request), params=params)
    return {"agents": result.data, "tier": result.tier_served.value}


# -- Grid Endpoints (DOC-015) --

@app.get("/v1/grid/nodes")
async def list_grid_nodes(state: Optional[str] = None):
    nodes = grid_sm.active_nodes if grid_sm else []
    if state: nodes = [n for n in nodes if n.state.value == state]
    return {"nodes": [{"node_id": n.node_id, "grid_address": n.grid_address,
                       "node_type": n.node_type, "state": n.state.value,
                       "health_score": n.health_score, "dashboard_color": n.dashboard_color,
                       "routes_traffic": n.routes_traffic,
                       "time_since_heartbeat": round(n.time_since_heartbeat, 1),
                       "failure_count": n.failure_count}
                      for n in nodes], "total": len(nodes)}

@app.get("/v1/grid/health-scores")
async def grid_health_scores():
    if not grid_sm or not health_scorer: return {"distribution": {}}
    scores = {}
    for node in grid_sm.active_nodes:
        b = health_scorer.calculate(node)
        scores.setdefault(b.classification.value, []).append(
            {"node_id": node.node_id, "grid_address": node.grid_address, "score": round(b.total, 1)})
    return {"distribution": scores}

@app.get("/v1/grid/cemetery")
async def grid_cemetery():
    return {"reports": coroner.get_reports() if coroner else [],
            "analytics": coroner.get_death_analytics() if coroner else {}}

@app.get("/v1/grid/ggc/stats")
async def ggc_stats():
    return ggc.get_stats() if ggc else {}

@app.get("/v1/grid/resurrections")
async def resurrection_events():
    return {"events": resurrection.get_events() if resurrection else []}


# -- ASA Endpoints (DOC-015) --

@app.get("/v1/asa/standards")
async def list_standards(category: Optional[str] = None):
    standards = asa.get_all_standards(category=category) if asa else []
    return {"standards": [{"standard_id": s.standard_id, "category": s.category,
                           "title": s.title, "description": s.description,
                           "enforcement": s.enforcement.value, "source_document": s.source_document}
                          for s in standards]}

@app.get("/v1/asa/violations")
async def list_violations():
    return {"violations": asa.get_violations() if asa else [],
            "stats": asa.get_violation_stats() if asa else {}}


# -- Heartbeat Endpoints (DOC-014) --

@app.get("/v1/heartbeat/status")
async def heartbeat_status():
    return heartbeat.get_status() if heartbeat else {}

@app.get("/v1/heartbeat/circuit-breakers")
async def circuit_breaker_status():
    return {"breakers": circuits.get_all_status() if circuits else [],
            "open_circuits": circuits.get_open_circuits() if circuits else []}

@app.get("/v1/heartbeat/health-history")
async def health_history(tier: Optional[int] = None):
    from cortexdb.heartbeat.health_checks import HealthTier
    t = HealthTier(tier) if tier else None
    return {"history": health_runner.get_history(t) if health_runner else []}

@app.get("/v1/ledger/recent")
async def recent_ledger(limit: int = 20):
    if "immutable" in db.engines:
        entries = db.engines["immutable"]._chain[-limit:]
        return {"entries": entries, "total": len(db.engines["immutable"]._chain)}
    return {"error": "ImmutableCore not connected"}


# -- MCP Server Endpoints (DOC-017 Section 10, DOC-018 G18) --

@app.get("/v1/mcp/tools")
async def mcp_list_tools():
    return {"tools": mcp_server.list_tools() if mcp_server else [],
            "server_info": mcp_server.get_server_info() if mcp_server else {}}

@app.post("/v1/mcp/call")
async def mcp_call_tool(req: MCPToolCallRequest):
    if not mcp_server:
        raise HTTPException(503, "MCP Server not initialized")
    result = await mcp_server.call_tool(req.tool, req.input)
    if result.is_error:
        raise HTTPException(400, result.error_message)
    return {"result": result.content}


# -- A2A Endpoints (DOC-017 Section 10, DOC-018 G19) --

@app.post("/v1/a2a/register")
async def a2a_register(req: AgentCardRequest, request: Request):
    card = AgentCard(
        agent_id=req.agent_id, name=req.name, description=req.description,
        skills=req.skills, tools=req.tools, endpoint_url=req.endpoint_url,
        protocol=req.protocol, model=req.model,
        tenant_id=_tenant_id(request))
    result = await a2a_registry.register(card)
    return result

@app.get("/v1/a2a/discover")
async def a2a_discover(skill: str, request: Request, limit: int = 5):
    return {"agents": await a2a_registry.discover(
        skill, tenant_id=_tenant_id(request), limit=limit)}

@app.get("/v1/a2a/agents")
async def a2a_list_agents(request: Request):
    return {"agents": a2a_registry.list_cards(tenant_id=_tenant_id(request))}

@app.post("/v1/a2a/heartbeat/{agent_id}")
async def a2a_heartbeat(agent_id: str):
    ok = await a2a_registry.heartbeat(agent_id)
    return {"status": "ok" if ok else "not_found"}

@app.post("/v1/a2a/task")
async def a2a_create_task(req: A2ATaskRequest, request: Request):
    task = await a2a_protocol.create_task(
        source_agent_id=req.source_agent_id,
        target_agent_id=req.target_agent_id,
        skill=req.skill, input_data=req.input_data,
        tenant_id=_tenant_id(request), priority=req.priority)
    return {"task_id": task.task_id, "status": task.status.value}

@app.get("/v1/a2a/tasks")
async def a2a_list_tasks(request: Request, agent_id: Optional[str] = None,
                         status: Optional[str] = None):
    return {"tasks": a2a_protocol.list_tasks(
        agent_id=agent_id, status=status,
        tenant_id=_tenant_id(request))}

@app.post("/v1/a2a/task/{task_id}/complete")
async def a2a_complete_task(task_id: str, output: Dict):
    task = await a2a_protocol.complete_task(task_id, output)
    if not task:
        raise HTTPException(404, "Task not found or not in running state")
    return {"task_id": task.task_id, "status": task.status.value}


# -- CortexGraph Endpoints (DOC-020) --

@app.post("/v1/cortexgraph/identify")
async def cg_identify(req: IdentifyRequest, request: Request):
    """Identity resolution: resolve identifiers to a customer_id."""
    tid = _tenant_id(request)
    result = await identity_resolver.identify(
        req.identifiers, tenant_id=tid, attributes=req.attributes)
    return result

@app.post("/v1/cortexgraph/track")
async def cg_track(req: TrackEventRequest, request: Request):
    """Track a customer event across all engines."""
    tid = _tenant_id(request)
    result = await event_tracker.track(
        customer_id=req.customer_id, event_type=req.event_type,
        properties=req.properties, source=req.source,
        session_id=req.session_id, channel=req.channel, tenant_id=tid)
    return result

@app.post("/v1/cortexgraph/track/batch")
async def cg_track_batch(req: TrackBatchRequest, request: Request):
    """Batch track multiple customer events."""
    tid = _tenant_id(request)
    result = await event_tracker.track_batch(req.events, tenant_id=tid)
    return result

@app.get("/v1/cortexgraph/customer/{customer_id}/360")
async def cg_customer_360(customer_id: str, request: Request):
    """Complete customer intelligence: identity + events + relationships + profile."""
    tid = _tenant_id(request)
    return await cortexgraph.customer_360(customer_id, tenant_id=tid)

@app.get("/v1/cortexgraph/customer/{customer_id}/profile")
async def cg_customer_profile(customer_id: str, request: Request):
    """Get or compute behavioral profile for a customer."""
    tid = _tenant_id(request)
    profile = await profiler.get_profile(customer_id, tenant_id=tid)
    return {"customer_id": customer_id, "profile": profile}

@app.get("/v1/cortexgraph/customer/{customer_id}/events")
async def cg_customer_events(customer_id: str, request: Request,
                              event_type: Optional[str] = None,
                              days: int = 90, limit: int = 100):
    """Query events for a customer."""
    tid = _tenant_id(request)
    events = await event_tracker.query_events(
        customer_id, event_type=event_type, days=days,
        tenant_id=tid, limit=limit)
    return {"customer_id": customer_id, "events": events}

@app.get("/v1/cortexgraph/customer/{customer_id}/connections")
async def cg_customer_connections(customer_id: str, request: Request):
    """Get all graph connections for a customer."""
    tid = _tenant_id(request)
    connections = await relationship_graph.get_customer_connections(customer_id, tid)
    return {"customer_id": customer_id, "connections": connections}

@app.get("/v1/cortexgraph/similar/{customer_id}")
async def cg_similar_customers(customer_id: str, request: Request, limit: int = 50):
    """Find customers with similar behavioral patterns."""
    tid = _tenant_id(request)
    results = await cortexgraph.find_similar_customers(customer_id, limit, tid)
    return {"customer_id": customer_id, "similar": results}

@app.get("/v1/cortexgraph/churn-risk")
async def cg_churn_risk(request: Request, threshold: float = 0.7, limit: int = 50):
    """Get customers at risk of churning."""
    tid = _tenant_id(request)
    results = await cortexgraph.get_churn_risk_customers(threshold, tid, limit)
    return {"at_risk": results, "threshold": threshold}

@app.post("/v1/cortexgraph/recommend/{customer_id}")
async def cg_recommend(customer_id: str, request: Request, limit: int = 5):
    """Product recommendations via collaborative filtering."""
    tid = _tenant_id(request)
    results = await cortexgraph.recommend_products(customer_id, limit, tid)
    return {"customer_id": customer_id, "recommendations": results}

@app.get("/v1/cortexgraph/attribution/{campaign_id}")
async def cg_attribution(campaign_id: str, request: Request):
    """Campaign attribution analysis."""
    tid = _tenant_id(request)
    return await cortexgraph.campaign_attribution(campaign_id, tid)

@app.post("/v1/cortexgraph/merge")
async def cg_merge(req: MergeCustomersRequest, request: Request):
    """Merge two customer records."""
    result = await identity_resolver.merge(
        req.canonical_id, req.duplicate_id, req.reason)
    return result

@app.get("/v1/cortexgraph/stats")
async def cg_stats():
    """CortexGraph component statistics."""
    return cortexgraph.get_stats() if cortexgraph else {}

@app.post("/v1/cortexgraph/profiles/compute-all")
async def cg_compute_all_profiles(request: Request, limit: int = 1000):
    """Batch compute all customer profiles (Sleep Cycle trigger)."""
    tid = _tenant_id(request)
    result = await profiler.compute_all(tenant_id=tid, limit=limit)
    return result


# -- Bridge Endpoints (DOC-018 G9) --

@app.post("/v1/bridge/query")
async def bridge_query(sub_queries: List[Dict], merge_key: Optional[str] = None):
    if not db or not db.bridge:
        raise HTTPException(503, "Bridge not initialized")
    return await db.bridge.query(sub_queries, merge_key)


# -- Scale: Sharding Endpoints (Citus) --

@app.post("/v1/admin/sharding/initialize")
async def sharding_init(request: Request):
    """Initialize Citus extension and sharding configuration."""
    _verify_admin(request)
    return await shard_mgr.initialize() if shard_mgr else {"error": "not available"}

@app.post("/v1/admin/sharding/distribute")
async def sharding_distribute(request: Request):
    """Distribute all tables across Citus workers."""
    _verify_admin(request)
    return await shard_mgr.distribute_tables() if shard_mgr else {"error": "not available"}

@app.post("/v1/admin/sharding/add-worker")
async def sharding_add_worker(request: Request, host: str = "", port: int = 5432):
    """Add a Citus worker node."""
    _verify_admin(request)
    import re
    if not re.match(r'^[a-zA-Z0-9._-]+$', host) or len(host) > 253:
        raise HTTPException(400, "Invalid hostname format")
    if not (1 <= port <= 65535):
        raise HTTPException(400, "Port must be 1-65535")
    return await shard_mgr.add_worker(host, port) if shard_mgr else {"error": "not available"}

@app.post("/v1/admin/sharding/remove-worker")
async def sharding_remove_worker(request: Request, host: str = "", port: int = 5432):
    """Remove a Citus worker node (drains shards first)."""
    _verify_admin(request)
    import re
    if not re.match(r'^[a-zA-Z0-9._-]+$', host) or len(host) > 253:
        raise HTTPException(400, "Invalid hostname format")
    if not (1 <= port <= 65535):
        raise HTTPException(400, "Port must be 1-65535")
    return await shard_mgr.remove_worker(host, port) if shard_mgr else {"error": "not available"}

@app.post("/v1/admin/sharding/rebalance")
async def sharding_rebalance(request: Request):
    """Rebalance shards across workers."""
    _verify_admin(request)
    if not shard_mgr:
        return {"error": "not available"}
    result = await shard_mgr.rebalance()
    return {"moved": result.moved, "errors": result.errors,
            "duration_ms": result.duration_ms}

@app.get("/v1/admin/sharding/stats")
async def sharding_stats(request: Request):
    """Get shard distribution statistics."""
    _verify_admin(request)
    return await shard_mgr.get_shard_stats() if shard_mgr else shard_mgr.get_stats()

@app.get("/v1/admin/sharding/tenant-placement/{tenant_id}")
async def sharding_tenant_placement(tenant_id: str, request: Request):
    """Find which worker hosts a tenant's data."""
    _verify_admin(request)
    return await shard_mgr.get_tenant_placement(tenant_id) if shard_mgr else {}

@app.post("/v1/admin/sharding/isolate-tenant/{tenant_id}")
async def sharding_isolate_tenant(tenant_id: str, request: Request):
    """Isolate a premium tenant onto dedicated shard."""
    _verify_admin(request)
    return await shard_mgr.isolate_tenant(tenant_id) if shard_mgr else {}

@app.post("/v1/admin/sharding/columnar/{table_name}")
async def sharding_enable_columnar(table_name: str, request: Request):
    """Convert a table to Citus columnar storage for analytics."""
    _verify_admin(request)
    return await shard_mgr.enable_columnar(table_name) if shard_mgr else {}


# -- Scale: Replica Routing Endpoints (admin-protected) --

@app.get("/v1/admin/replicas/stats")
async def replica_stats(request: Request):
    """Get read replica routing statistics."""
    _verify_admin(request)
    return replica_router.get_stats() if replica_router else {}

@app.get("/v1/admin/replicas/lag")
async def replica_lag(request: Request):
    """Check replication lag on all replicas."""
    _verify_admin(request)
    return await replica_router.check_replica_lag() if replica_router else []

@app.get("/v1/admin/replicas/pool")
async def replica_pool_stats(request: Request):
    """Get connection pool statistics."""
    _verify_admin(request)
    return await replica_router.get_pool_stats() if replica_router else {}


# -- Scale: AI Index Management Endpoints (admin-protected) --

@app.get("/v1/admin/indexes/slow-queries")
async def index_slow_queries(request: Request, limit: int = 50):
    """Analyze slow queries for index recommendations."""
    _verify_admin(request)
    limit = max(1, min(limit, 200))
    return await ai_index.analyze_slow_queries(limit) if ai_index else []

@app.get("/v1/admin/indexes/recommend")
async def index_recommend(request: Request):
    """Get AI-powered index recommendations."""
    _verify_admin(request)
    recs = await ai_index.recommend() if ai_index else []
    return {"recommendations": [
        {"table": r.table, "columns": r.columns, "type": r.index_type.value,
         "reason": r.reason, "priority": r.priority, "speedup": r.estimated_speedup}
        for r in recs
    ]}

@app.post("/v1/admin/indexes/create")
async def index_create(request: Request, concurrently: bool = True):
    """Create recommended indexes (CONCURRENTLY = no locks)."""
    _verify_admin(request)
    if not ai_index:
        return {"error": "not available"}
    await ai_index.recommend()
    return await ai_index.create_optimal(concurrently=concurrently)

@app.post("/v1/admin/indexes/tune-vector")
async def index_tune_vector(request: Request, collection: Optional[str] = None):
    """Auto-tune HNSW/IVF vector index parameters."""
    _verify_admin(request)
    return await ai_index.tune_vector_indexes(collection) if ai_index else {}

@app.get("/v1/admin/indexes/garbage-collect")
async def index_gc(request: Request):
    """Find unused and duplicate indexes."""
    _verify_admin(request)
    return await ai_index.garbage_collect() if ai_index else {}

@app.get("/v1/admin/indexes/stats")
async def index_stats(request: Request):
    """AI index manager statistics."""
    _verify_admin(request)
    return ai_index.get_stats() if ai_index else {}


# -- Scale: Data Rendering Endpoints (admin-protected) --

@app.post("/v1/admin/views/setup")
async def views_setup(request: Request):
    """Create all CortexDB materialized views."""
    _verify_admin(request)
    return await data_renderer.setup_materialized_views() if data_renderer else {}

@app.post("/v1/admin/views/refresh")
async def views_refresh(request: Request, force: bool = False):
    """Refresh stale materialized views."""
    _verify_admin(request)
    return await data_renderer.refresh_views(force) if data_renderer else {}

@app.get("/v1/admin/views/stats")
async def views_stats(request: Request):
    """Get materialized view statistics."""
    _verify_admin(request)
    return await data_renderer.get_view_stats() if data_renderer else []

@app.get("/v1/admin/rendering/stats")
async def rendering_stats(request: Request):
    """Data rendering pipeline statistics."""
    _verify_admin(request)
    return data_renderer.get_stats() if data_renderer else {}


# -- Compliance: Framework Endpoints --

@app.get("/v1/compliance/audit")
async def compliance_audit_all():
    """Run compliance audit across all frameworks."""
    if not compliance:
        return {"error": "not available"}
    report = await compliance.audit()
    return {"score": report.score, "total": report.total_controls,
            "compliant": report.compliant, "partial": report.partial,
            "non_compliant": report.non_compliant,
            "gaps": report.gaps}

@app.get("/v1/compliance/audit/{framework}")
async def compliance_audit_framework(framework: str):
    """Run compliance audit for a specific framework."""
    if not compliance:
        return {"error": "not available"}
    try:
        fw = Framework(framework)
    except ValueError:
        raise HTTPException(400, f"Unknown framework: {framework}. "
                            f"Valid: fedramp, soc2, hipaa, pci_dss, pa_dss")
    report = await compliance.audit(fw)
    return {"framework": framework, "score": report.score,
            "total": report.total_controls, "compliant": report.compliant,
            "controls": report.controls, "gaps": report.gaps}

@app.get("/v1/compliance/summary")
async def compliance_summary():
    """Get compliance framework summary."""
    return compliance.get_framework_summary() if compliance else {}

@app.get("/v1/compliance/stats")
async def compliance_stats():
    """Compliance engine statistics."""
    return compliance.get_stats() if compliance else {}


# -- Compliance: Encryption Endpoints --

@app.get("/v1/compliance/encryption/stats")
async def encryption_stats():
    """Field encryption statistics and key health."""
    return field_encryption.get_stats() if field_encryption else {}

@app.get("/v1/compliance/encryption/classification/{table}")
async def encryption_classification(table: str):
    """Get field sensitivity classification for a table."""
    return field_encryption.get_classification(table) if field_encryption else {}

@app.post("/v1/compliance/encryption/rotate-keys")
async def encryption_rotate(request: Request):
    """Rotate encryption keys that are due. Requires admin auth."""
    # Require admin authentication
    tid = getattr(request.state, "tenant_id", None)
    if tid != "__admin__":
        raise HTTPException(403, {"error": "forbidden", "message": "Admin access required"})
    if not field_encryption:
        return {"error": "not available"}
    due = field_encryption.key_manager.check_rotation_needed()
    rotated = []
    for key_id in due:
        field_encryption.key_manager.rotate_key(key_id)
        rotated.append(key_id)
    if compliance_audit:
        for key_id in rotated:
            await compliance_audit.log(
                AuditEventType.ENCRYPTION_KEY_ROTATED,
                actor="admin", resource=key_id, action="key_rotation")
    return {"rotated": rotated, "count": len(rotated)}


# -- Compliance: Audit Trail Endpoints --

@app.get("/v1/compliance/audit-log")
async def audit_log(event_type: Optional[str] = None,
                    actor: Optional[str] = None,
                    tenant_id: Optional[str] = None,
                    severity: Optional[str] = None,
                    limit: int = 100):
    """Query compliance audit trail."""
    if not compliance_audit:
        return {"events": []}
    et = AuditEventType(event_type) if event_type else None
    from cortexdb.compliance.audit import AuditSeverity
    sev = AuditSeverity(severity) if severity else None
    events = compliance_audit.query_events(
        event_type=et, actor=actor, tenant_id=tenant_id,
        severity=sev, limit=limit)
    return {"events": events, "count": len(events)}

@app.get("/v1/compliance/evidence/{framework}")
async def compliance_evidence(framework: str):
    """Generate compliance evidence report for auditors."""
    if not compliance_audit:
        return {"error": "not available"}
    return await compliance_audit.generate_evidence_report(framework)

@app.get("/v1/compliance/audit-log/stats")
async def audit_log_stats():
    """Audit trail statistics."""
    return compliance_audit.get_stats() if compliance_audit else {}


# ── Benchmark Endpoints ──

from cortexdb.benchmark.runner import BenchmarkRunner
from cortexdb.benchmark.stress import StressTestEngine, StressConfig, StressPattern

_bench_runner = BenchmarkRunner()
_stress_engine = StressTestEngine()


@app.post("/v1/admin/benchmark/run")
async def run_benchmark(
    suite: str = "quick",
    concurrency: int = 10,
    iterations: int = 1000,
):
    """Run built-in benchmark suite. suite: 'quick' or 'full'."""
    from cortexdb.benchmark.scenarios import ScenarioRegistry
    registry = ScenarioRegistry(db=db, engines={})
    scenarios = registry.get_quick_scenarios() if suite == "quick" else registry.get_all_scenarios()
    for s in scenarios:
        s["concurrency"] = concurrency
        if suite == "quick":
            s["iterations"] = min(iterations, 500)
    return await _bench_runner.run_suite(scenarios, concurrency=concurrency)


@app.get("/v1/admin/benchmark/results")
async def benchmark_results():
    """Get results from the last benchmark run."""
    return _bench_runner.get_results()


@app.post("/v1/admin/benchmark/stress")
async def run_stress_test(
    pattern: str = "ramp",
    duration_sec: int = 30,
    base_rps: int = 100,
    peak_rps: int = 500,
):
    """Run a stress test pattern (spike/soak/ramp/burst/mixed)."""
    if _stress_engine.is_running():
        return {"error": "Stress test already running"}
    valid_patterns = {"spike", "soak", "ramp", "burst", "mixed"}
    if pattern not in valid_patterns:
        raise HTTPException(400, f"Invalid pattern. Must be one of: {valid_patterns}")
    duration_sec = max(5, min(duration_sec, 300))
    base_rps = max(1, min(base_rps, 5000))
    peak_rps = max(base_rps, min(peak_rps, 10000))

    config = StressConfig(
        pattern=StressPattern(pattern),
        duration_sec=duration_sec,
        base_rps=base_rps,
        peak_rps=peak_rps,
    )

    async def _read():
        if db:
            await db.query("SELECT 1", tenant_id="__benchmark__")
        return {"ok": True}

    async def _write():
        if db:
            await db.query("SELECT 1", tenant_id="__benchmark__")
        return {"ok": True}

    result = await _stress_engine.run(config, _read, _write)
    return result.to_dict()


@app.post("/v1/admin/benchmark/stop")
async def stop_benchmark():
    """Stop any running benchmark or stress test."""
    _bench_runner.stop()
    _stress_engine.stop()
    return {"stopped": True}


# ── Budget & Forecasting ─────────────────────────────────

@app.get("/v1/budget/summary")
async def get_budget_summary():
    """Get overall budget summary with alerts."""
    return budget_tracker.get_summary()


@app.get("/v1/budget/resources")
async def get_budget_resources():
    """Get all resource budgets with usage."""
    return {"budgets": budget_tracker.get_budgets()}


@app.get("/v1/budget/resources/{resource}")
async def get_budget_resource(resource: str):
    """Get specific resource budget."""
    b = budget_tracker.get_budget(resource)
    if not b:
        raise HTTPException(404, f"Resource '{resource}' not found")
    return b


@app.post("/v1/budget/resources/{resource}")
async def set_budget_resource(resource: str, request: Request):
    """Update resource budget allocation."""
    body = await request.json()
    allocated = body.get("allocated")
    if allocated is None:
        raise HTTPException(400, "Missing 'allocated' field")
    return budget_tracker.set_budget(resource, float(allocated))


@app.get("/v1/budget/tenants")
async def get_budget_tenants():
    """Get per-tenant cost breakdown."""
    return {"tenants": budget_tracker.get_tenant_costs()}


@app.get("/v1/budget/tenants/{tenant_id}")
async def get_budget_tenant(tenant_id: str):
    """Get specific tenant cost breakdown."""
    t = budget_tracker.get_tenant_cost(tenant_id)
    if not t:
        raise HTTPException(404, f"Tenant '{tenant_id}' not found")
    return t


@app.get("/v1/budget/history")
async def get_budget_history(resource: Optional[str] = None, days: int = 30):
    """Get usage history for forecasting."""
    return {"history": budget_tracker.get_usage_history(resource, days)}


@app.get("/v1/budget/monthly")
async def get_budget_monthly():
    """Get monthly cost totals."""
    return {"months": budget_tracker.get_monthly_totals()}


@app.post("/v1/budget/record")
async def record_budget_usage(request: Request):
    """Record a usage data point."""
    body = await request.json()
    budget_tracker.record_usage(
        resource=body["resource"],
        value=float(body["value"]),
        tenant_id=body.get("tenant_id"),
    )
    return {"status": "recorded"}


# ── AI Forecasting Agent ─────────────────────────────────

@app.post("/v1/forecast/run")
async def run_forecast():
    """Run AI forecasting analysis. Analyzes usage trends, detects anomalies, generates predictions."""
    return await forecasting_agent.run_analysis()


@app.get("/v1/forecast/latest")
async def get_latest_forecast():
    """Get results from the most recent forecasting run."""
    return forecasting_agent.get_last_forecast()


@app.get("/v1/forecast/resource/{resource}")
async def get_resource_forecast(resource: str):
    """Get forecast for a specific resource."""
    data = forecasting_agent.get_last_forecast()
    if data.get("status") == "no_data":
        # Auto-run if no data yet
        data = await forecasting_agent.run_analysis()
    for f in data.get("forecasts", []):
        if f["resource"] == resource:
            return f
    raise HTTPException(404, f"No forecast for '{resource}'")


# ── Agent Registry ──────────────────────────────────────

@app.get("/v1/agents/registry")
async def get_all_agents():
    """Get all registered agents with status and metadata."""
    return {"agents": agent_registry.get_all_agents(), "summary": agent_registry.get_summary()}


@app.get("/v1/agents/registry/{agent_id}")
async def get_agent_detail(agent_id: str):
    """Get details for a specific agent."""
    data = agent_registry.get_agent(agent_id)
    if not data:
        raise HTTPException(404, f"Agent '{agent_id}' not found")
    return data


@app.get("/v1/agents/summary")
async def get_agents_summary():
    """Get agent registry summary."""
    return agent_registry.get_summary()


# ── System Metrics Agent ────────────────────────────────

@app.get("/v1/metrics/system")
async def get_system_metrics():
    """Get current system metrics (CPU, RAM, disk, network)."""
    agent_registry.record_run("AGT-SYS-001", 0)
    return system_metrics_agent.collect()


@app.get("/v1/metrics/system/history")
async def get_system_metrics_history(minutes: int = 30):
    """Get system metrics history."""
    return {"history": system_metrics_agent.get_history(minutes)}


@app.get("/v1/metrics/hardware")
async def get_hardware_summary():
    """Get hardware summary (platform, CPU, memory, disk, network)."""
    return system_metrics_agent.get_hardware_summary()


# ── Database Monitor Agent ──────────────────────────────

@app.get("/v1/monitor/db")
async def get_db_monitor():
    """Get current database monitoring metrics."""
    agent_registry.record_run("AGT-DB-001", 0)
    return db_monitor_agent.get_current()


@app.get("/v1/monitor/db/summary")
async def get_db_summary():
    """Get database monitoring summary."""
    return db_monitor_agent.get_summary()


@app.get("/v1/monitor/db/slow-queries")
async def get_db_slow_queries():
    """Get active slow queries."""
    return {"queries": db_monitor_agent.get_slow_queries()}


@app.get("/v1/monitor/db/locks")
async def get_db_locks():
    """Get active database locks."""
    return {"locks": db_monitor_agent.get_locks()}


@app.get("/v1/monitor/db/history")
async def get_db_history(minutes: int = 30):
    """Get database metrics history."""
    return {"history": db_monitor_agent.get_history(minutes)}


@app.get("/v1/monitor/db/pool")
async def get_db_pool():
    """Get connection pool stats."""
    return db_monitor_agent.get_pool_stats()


# ── Service Monitor Agent ───────────────────────────────

@app.get("/v1/monitor/services")
async def get_all_services():
    """Get all microservice statuses."""
    agent_registry.record_run("AGT-SVC-001", 0)
    return {"services": service_monitor_agent.collect()}


@app.get("/v1/monitor/services/summary")
async def get_services_summary():
    """Get services summary."""
    return service_monitor_agent.get_summary()


@app.get("/v1/monitor/services/{name}")
async def get_service_detail(name: str):
    """Get details for a specific service."""
    data = service_monitor_agent.get_service(name)
    if not data:
        raise HTTPException(404, f"Service '{name}' not found")
    return data


@app.get("/v1/monitor/services/dependencies")
async def get_service_dependencies():
    """Get service dependency map."""
    return {"dependencies": service_monitor_agent.get_dependency_map()}


# ── Security Agent ──────────────────────────────────────

@app.get("/v1/security/overview")
async def get_security_overview():
    """Get security overview with threat level and scores."""
    agent_registry.record_run("AGT-SEC-001", 0)
    return security_agent.collect()


@app.get("/v1/security/threats")
async def get_security_threats(severity: str = None, limit: int = 50):
    """Get threat events."""
    return {"threats": security_agent.get_threats(severity, limit)}


@app.get("/v1/security/threats/stats")
async def get_threat_stats():
    """Get threat statistics."""
    return security_agent.get_threat_stats()


@app.get("/v1/security/audit")
async def get_security_audit_log(limit: int = 50):
    """Get security audit log."""
    return {"entries": security_agent.get_audit_log(limit)}


# ── Error Tracking Agent ────────────────────────────────

@app.get("/v1/errors")
async def get_all_errors(level: str = None):
    """Get all tracked errors."""
    agent_registry.record_run("AGT-ERR-001", 0)
    resolved = None  # show all
    return {"errors": error_tracking_agent.get_all_errors(level, resolved)}


@app.get("/v1/errors/summary")
async def get_error_summary():
    """Get error tracking summary."""
    return error_tracking_agent.collect()


@app.get("/v1/errors/{error_id}")
async def get_error_detail(error_id: str):
    """Get details for a specific error."""
    data = error_tracking_agent.get_error(error_id)
    if not data:
        raise HTTPException(404, f"Error '{error_id}' not found")
    return data


@app.post("/v1/errors/{error_id}/resolve")
async def resolve_error(error_id: str, request: Request):
    """Resolve an error with a resolution note."""
    body = await request.json()
    result = error_tracking_agent.resolve_error(error_id, body.get("resolution", ""))
    if not result:
        raise HTTPException(404, f"Error '{error_id}' not found")
    return result


@app.get("/v1/errors/by-service")
async def get_errors_by_service(request: Request):
    """Get error counts grouped by service."""
    _verify_admin(request)
    return {"services": error_tracking_agent.get_stats_by_service()}


# ── Notification Agent ──────────────────────────────────

@app.get("/v1/notifications")
async def get_notifications(request: Request, severity: str = None, category: str = None,
                            unread_only: bool = False, limit: int = 50):
    """Get notifications with optional filtering."""
    _verify_admin(request)
    agent_registry.record_run("AGT-NTF-001", 0)
    # Generate new notification on each poll
    notification_agent.generate()
    return {"notifications": notification_agent.get_all(severity, category, unread_only, limit)}


@app.get("/v1/notifications/summary")
async def get_notification_summary(request: Request):
    """Get notification summary."""
    _verify_admin(request)
    return notification_agent.get_summary()


@app.post("/v1/notifications/{notif_id}/read")
async def mark_notification_read(request: Request, notif_id: str):
    """Mark a notification as read."""
    _verify_admin(request)
    notification_agent.mark_read(notif_id)
    return {"status": "ok"}


@app.post("/v1/notifications/read-all")
async def mark_all_notifications_read(request: Request):
    """Mark all notifications as read."""
    _verify_admin(request)
    notification_agent.mark_all_read()
    return {"status": "ok"}


@app.post("/v1/notifications/{notif_id}/dismiss")
async def dismiss_notification(request: Request, notif_id: str):
    """Dismiss a notification."""
    _verify_admin(request)
    notification_agent.dismiss(notif_id)
    return {"status": "ok"}


# ── SuperAdmin Auth ─────────────────────────────────────

def _verify_superadmin(request: Request):
    """Verify superadmin session token from header."""
    token = request.headers.get("X-SuperAdmin-Token", "")
    if not superadmin_auth.validate_session(token):
        raise HTTPException(403, "Unauthorized — invalid or expired superadmin session")


@app.get("/v1/superadmin/migrations")
async def get_migration_status(request: Request):
    """Return applied and pending database migrations."""
    _verify_superadmin(request)
    status = await _migrator.get_status()
    return {"migrations": status, "total": len(status)}


@app.post("/v1/superadmin/login")
async def superadmin_login(request: Request):
    """Authenticate with passphrase."""
    body = await request.json()
    ip = request.client.host if request.client else "unknown"
    token = superadmin_auth.authenticate(body.get("passphrase", ""), ip)
    if not token:
        raise HTTPException(401, "Invalid passphrase or account locked")
    return {"token": token, "expires_in": 86400}


@app.post("/v1/superadmin/logout")
async def superadmin_logout(request: Request):
    token = request.headers.get("X-SuperAdmin-Token", "")
    superadmin_auth.revoke_session(token)
    return {"status": "logged_out"}


@app.get("/v1/superadmin/session")
async def superadmin_session(request: Request):
    token = request.headers.get("X-SuperAdmin-Token", "")
    info = superadmin_auth.get_session_info(token)
    if not info:
        raise HTTPException(401, "No valid session")
    return info


# ── SuperAdmin: Agent Team ──────────────────────────────

@app.get("/v1/superadmin/team")
async def get_team(request: Request):
    _verify_superadmin(request)
    return {"agents": agent_team.get_all_agents(), "summary": agent_team.get_summary()}


@app.get("/v1/superadmin/team/org-chart")
async def get_org_chart(request: Request):
    _verify_superadmin(request)
    return agent_team.get_org_chart()


@app.get("/v1/superadmin/team/{agent_id}")
async def get_team_agent(agent_id: str, request: Request):
    _verify_superadmin(request)
    data = agent_team.get_agent(agent_id)
    if not data:
        raise HTTPException(404, f"Agent '{agent_id}' not found")
    return data


@app.put("/v1/superadmin/team/{agent_id}")
async def update_team_agent(agent_id: str, request: Request):
    _verify_superadmin(request)
    body = await request.json()
    data = agent_team.update_agent(agent_id, body)
    if not data:
        raise HTTPException(404, f"Agent '{agent_id}' not found")
    return data


@app.get("/v1/superadmin/team/department/{dept}")
async def get_department(dept: str, request: Request):
    _verify_superadmin(request)
    return agent_team.get_department(dept)


# ── SuperAdmin: Tasks ───────────────────────────────────

@app.post("/v1/superadmin/tasks")
async def create_task(request: Request):
    _verify_superadmin(request)
    body = await request.json()
    task = agent_team.create_task(
        title=body["title"], description=body.get("description", ""),
        assigned_to=body.get("assigned_to"), priority=body.get("priority", "medium"),
        category=body.get("category", "general"), microservice=body.get("microservice", ""),
    )
    # Auto-enqueue for execution if assigned and auto_execute requested
    if body.get("auto_execute") and task.get("assigned_to"):
        await task_executor.enqueue(task["task_id"])
        task["queued_for_execution"] = True
    await _push_event("task_created", {"task_id": task["task_id"], "title": task["title"]})
    return task


@app.get("/v1/superadmin/tasks")
async def get_tasks(request: Request, status: str = None):
    _verify_superadmin(request)
    return {"tasks": agent_team.get_all_tasks(status)}


@app.get("/v1/superadmin/tasks/{task_id}")
async def get_task_detail(task_id: str, request: Request):
    _verify_superadmin(request)
    data = agent_team.get_task(task_id)
    if not data:
        raise HTTPException(404, f"Task '{task_id}' not found")
    return data


@app.put("/v1/superadmin/tasks/{task_id}")
async def update_task_detail(task_id: str, request: Request):
    _verify_superadmin(request)
    body = await request.json()
    data = agent_team.update_task(task_id, body)
    if not data:
        raise HTTPException(404, f"Task '{task_id}' not found")
    return data


# ── SuperAdmin: Auto-Delegation Intelligence ───────────

@app.post("/v1/superadmin/tasks/{task_id}/auto-assign")
async def auto_assign_task(task_id: str, request: Request):
    """Automatically assign a task to the best-fit agent based on skills, workload, and department."""
    _verify_superadmin(request)
    task = agent_team.get_task(task_id)
    if not task:
        raise HTTPException(404, "Task not found")

    agents = agent_team.get_all_agents()
    category = task.get("category", "general")
    microservice = task.get("microservice", "")

    # Score agents — hybrid: static rules + learned quality scores
    scored = []
    for a in agents:
        score = 0
        aid = a.get("agent_id", "")

        # Category match to department (static)
        dept = a.get("department", "")
        cat_dept_map = {
            "bug": "ENG", "feature": "ENG", "enhancement": "ENG",
            "qa": "QA", "docs": "DOC", "security": "SEC", "ops": "OPS",
        }
        if cat_dept_map.get(category) == dept:
            score += 20
        # Skill keyword match (static)
        skills = " ".join(a.get("skills", []) + a.get("responsibilities", [])).lower()
        if category.lower() in skills:
            score += 10
        if microservice and microservice.lower() in skills:
            score += 10
        # Workload: prefer idle agents (static)
        state = a.get("state", "idle")
        if state == "idle":
            score += 15
        elif state == "active":
            score += 5
        elif state == "working":
            score -= 10

        # LEARNED: Quality score for this agent on this category (0-30 points)
        agent_scores = outcome_analyzer.get_agent_scores(aid)
        cat_scores = agent_scores.get("by_category", {}).get(category, {})
        if cat_scores.get("total", 0) >= 2:
            # Learned quality: avg grade (1-10) maps to 0-30 points
            score += int(cat_scores.get("avg", 5) * 3)
        else:
            # Fallback to overall agent quality
            overall_avg = agent_scores.get("avg", 0)
            if overall_avg > 0:
                score += int(overall_avg * 2)
            else:
                # No data — use raw success rate as fallback
                completed = a.get("tasks_completed", 0)
                failed = a.get("tasks_failed", 0)
                if completed + failed > 0:
                    score += int((completed / (completed + failed)) * 15)

        # LEARNED: Check if this agent's prompt has been evolved (bonus for adapted agents)
        perf = prompt_evolution.get_prompt_performance(aid)
        if perf:
            agent_perf = list(perf.values())
            if any(p.get("avg_grade", 0) >= 7 for p in agent_perf):
                score += 5  # Bonus for agents with proven prompt effectiveness

        scored.append((a, score))

    scored.sort(key=lambda x: x[1], reverse=True)
    if not scored:
        return {"error": "No agents available"}

    best = scored[0][0]
    agent_team.update_task(task_id, {"assigned_to": best["agent_id"]})
    persistence_store.audit("auto_delegation", "task", task_id,
                            {"assigned_to": best["agent_id"], "score": scored[0][1]})

    return {
        "task_id": task_id,
        "assigned_to": best["agent_id"],
        "agent_name": best.get("name", ""),
        "score": scored[0][1],
        "candidates": [{"agent_id": a["agent_id"], "name": a.get("name", ""), "score": s}
                        for a, s in scored[:5]],
    }


# ── SuperAdmin: Task Approval Workflow ──────────────────

@app.post("/v1/superadmin/tasks/{task_id}/submit-for-approval")
async def submit_for_approval(task_id: str, request: Request):
    """Submit a task for approval before execution."""
    _verify_superadmin(request)
    task = agent_team.get_task(task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    agent_team.update_task(task_id, {
        "status": "awaiting_approval",
        "submitted_at": time.time(),
    })
    persistence_store.audit("task_submitted_for_approval", "task", task_id)
    return {"status": "awaiting_approval", "task_id": task_id}

@app.post("/v1/superadmin/tasks/{task_id}/approve")
async def approve_task(task_id: str, request: Request):
    """Approve a task. Optionally auto-execute."""
    _verify_superadmin(request)
    body = await request.json() if request.headers.get("content-length", "0") != "0" else {}
    task = agent_team.get_task(task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    agent_team.update_task(task_id, {
        "status": "approved",
        "approved_at": time.time(),
        "approved_by": "superadmin",
    })
    persistence_store.audit("task_approved", "task", task_id)
    if body.get("auto_execute") and task.get("assigned_to"):
        await task_executor.enqueue(task_id)
        return {"status": "approved", "queued": True}
    return {"status": "approved", "queued": False}

@app.post("/v1/superadmin/tasks/{task_id}/reject")
async def reject_task(task_id: str, request: Request):
    """Reject a task."""
    _verify_superadmin(request)
    body = await request.json() if request.headers.get("content-length", "0") != "0" else {}
    task = agent_team.get_task(task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    agent_team.update_task(task_id, {
        "status": "rejected",
        "rejected_at": time.time(),
        "rejection_reason": body.get("reason", ""),
    })
    persistence_store.audit("task_rejected", "task", task_id, {"reason": body.get("reason", "")})
    return {"status": "rejected", "task_id": task_id}

@app.get("/v1/superadmin/tasks/awaiting-approval")
async def get_tasks_awaiting_approval(request: Request):
    _verify_superadmin(request)
    tasks = [t for t in agent_team.get_all_tasks() if t.get("status") == "awaiting_approval"]
    return {"tasks": tasks, "count": len(tasks)}


# ── SuperAdmin: Task Pipelines ──────────────────────────

@app.post("/v1/superadmin/pipelines")
async def create_pipeline(request: Request):
    """Create a pipeline of chained tasks that execute sequentially."""
    _verify_superadmin(request)
    body = await request.json()
    pipeline_name = body.get("name", "Unnamed Pipeline")
    steps = body.get("steps", [])  # [{title, description, assigned_to, ...}, ...]

    if len(steps) < 2:
        raise HTTPException(400, "Pipeline requires at least 2 steps")

    # Create all tasks
    task_ids = []
    for step in steps:
        task = agent_team.create_task(
            title=step.get("title", "Pipeline Step"),
            description=step.get("description", ""),
            assigned_to=step.get("assigned_to"),
            priority=step.get("priority", "medium"),
            category=step.get("category", "general"),
            microservice=step.get("microservice", ""),
        )
        agent_team.update_task(task["task_id"], {"pipeline": pipeline_name})
        task_ids.append(task["task_id"])

    # Chain tasks: each points to the next
    for i in range(len(task_ids) - 1):
        agent_team.update_task(task_ids[i], {"next_tasks": [task_ids[i + 1]]})

    # Auto-execute first task if requested
    if body.get("auto_execute") and steps[0].get("assigned_to"):
        await task_executor.enqueue(task_ids[0])

    return {
        "pipeline": pipeline_name,
        "task_ids": task_ids,
        "steps": len(task_ids),
        "auto_execute": body.get("auto_execute", False),
    }


# ── SuperAdmin: Instructions / Conversation ─────────────

@app.post("/v1/superadmin/instructions")
async def send_instruction(request: Request):
    """Send an instruction to an agent. Supports multi-turn via agent memory."""
    _verify_superadmin(request)
    body = await request.json()
    content = body.get("content", "")
    agent_id = body.get("agent_id")
    provider = body.get("provider", "ollama")
    model = body.get("model", "")
    multi_turn = body.get("multi_turn", True)

    # Create instruction record
    instr = agent_team.add_instruction(content, agent_id, provider, model)

    # Get agent system prompt if assigned
    system_prompt = None
    if agent_id:
        agent_data = agent_team.get_agent(agent_id)
        if agent_data:
            system_prompt = agent_data.get("system_prompt", "")
            # Inject memory context
            if agent_memory:
                mem_context = agent_memory.build_context(agent_id, include_history=False)
                if mem_context:
                    system_prompt += f"\n\n{mem_context}"

    # Build messages — include conversation history for multi-turn
    messages = []
    if multi_turn and agent_memory and agent_id:
        turns = agent_memory.get_recent_turns(agent_id, limit=10)
        for turn in turns:
            messages.append({"role": turn["role"], "content": turn["content"]})
    messages.append({"role": "user", "content": content})

    result = await llm_router.chat(provider, messages, model=model or None, system=system_prompt)

    # Update instruction with response
    response_text = result.get("message") or result.get("response") or result.get("error", "No response")
    status = "completed" if result.get("success") else "failed"
    agent_team.update_instruction(instr["instruction_id"], response_text, status)

    # Store in agent memory for multi-turn
    if agent_memory and agent_id:
        agent_memory.add_turn(agent_id, "user", content)
        if result.get("success"):
            agent_memory.add_turn(agent_id, "assistant", response_text[:1000])

    return {
        "instruction": agent_team.get_instructions(limit=1)[0] if agent_team.get_instructions(limit=1) else instr,
        "llm_result": result,
    }


@app.get("/v1/superadmin/instructions")
async def get_instructions(request: Request, agent_id: str = None, limit: int = 50):
    _verify_superadmin(request)
    return {"instructions": agent_team.get_instructions(agent_id, limit)}


# ── SuperAdmin: LLM Providers ──────────────────────────

@app.get("/v1/superadmin/llm/providers")
async def get_llm_providers(request: Request):
    _verify_superadmin(request)
    return {
        "providers": llm_router.get_providers_status(),
        "stats": llm_router.get_request_stats(),
    }


@app.post("/v1/superadmin/llm/configure")
async def configure_llm_provider(request: Request):
    _verify_superadmin(request)
    body = await request.json()
    provider = body.get("provider", "")
    llm_router.configure_provider(provider, body)
    # Encrypt and persist API key
    if secrets_vault and secrets_vault.is_initialized and body.get("api_key"):
        encrypted_config = secrets_vault.encrypt_dict(body, ["api_key"])
        persistence_store.kv_set(f"llm_config:{provider}", encrypted_config)
    return {"status": "configured", "provider": provider}


@app.get("/v1/superadmin/llm/ollama/health")
async def ollama_health(request: Request):
    _verify_superadmin(request)
    return await ollama_client.check_health()


@app.get("/v1/superadmin/llm/ollama/models")
async def ollama_models(request: Request):
    _verify_superadmin(request)
    models = await ollama_client.list_models()
    return {"models": models}


# ── SuperAdmin: SSE Streaming Chat ─────────────────────

@app.post("/v1/superadmin/llm/chat/stream")
async def stream_chat(request: Request):
    """Stream LLM response via Server-Sent Events."""
    from starlette.responses import StreamingResponse
    import json as _json

    _verify_superadmin(request)
    body = await request.json()
    provider = body.get("provider", "ollama")
    messages = body.get("messages", [])
    system = body.get("system")
    model = body.get("model")
    temperature = body.get("temperature", 0.7)

    async def event_generator():
        try:
            async for token in llm_router.chat_stream(
                provider, messages, model=model, system=system, temperature=temperature
            ):
                yield f"data: {_json.dumps({'token': token})}\n\n"
            yield f"data: {_json.dumps({'done': True})}\n\n"
        except Exception as e:
            yield f"data: {_json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ── SuperAdmin: Task Executor ──────────────────────────

@app.post("/v1/superadmin/tasks/{task_id}/execute")
async def execute_task(task_id: str, request: Request):
    """Execute a task immediately via its assigned agent's LLM."""
    _verify_superadmin(request)
    result = await task_executor.execute_now(task_id)
    return result


@app.post("/v1/superadmin/tasks/execute-pending")
async def execute_pending_tasks(request: Request):
    """Queue all pending assigned tasks for execution."""
    _verify_superadmin(request)
    count = await task_executor.execute_pending()
    return {"queued": count}


@app.get("/v1/superadmin/executor/status")
async def executor_status(request: Request):
    _verify_superadmin(request)
    return task_executor.get_status()


# ── SuperAdmin: Agent Communication Bus ────────────────

@app.post("/v1/superadmin/bus/send")
async def bus_send_message(request: Request):
    """Send a message between agents."""
    _verify_superadmin(request)
    body = await request.json()
    msg = agent_bus.send(
        from_agent=body["from_agent"],
        to_agent=body["to_agent"],
        subject=body.get("subject", ""),
        content=body.get("content", ""),
        msg_type=body.get("msg_type", "direct"),
        priority=body.get("priority", "normal"),
        task_id=body.get("task_id"),
        parent_id=body.get("parent_id"),
        department=body.get("department"),
    )
    return msg


@app.post("/v1/superadmin/bus/delegate")
async def bus_delegate(request: Request):
    """Delegate a task from supervisor to subordinate."""
    _verify_superadmin(request)
    body = await request.json()
    msg = agent_bus.delegate(
        from_agent=body["from_agent"],
        to_agent=body["to_agent"],
        task_id=body["task_id"],
        instructions=body.get("instructions", ""),
    )
    return msg


@app.post("/v1/superadmin/bus/escalate")
async def bus_escalate(request: Request):
    """Escalate a task from subordinate to supervisor."""
    _verify_superadmin(request)
    body = await request.json()
    msg = agent_bus.escalate(
        from_agent=body["from_agent"],
        to_agent=body["to_agent"],
        task_id=body["task_id"],
        reason=body.get("reason", ""),
    )
    return msg


@app.post("/v1/superadmin/bus/broadcast")
async def bus_broadcast(request: Request):
    """Broadcast a message to all agents or a department."""
    _verify_superadmin(request)
    body = await request.json()
    msg = agent_bus.broadcast(
        from_agent=body.get("from_agent", "superadmin"),
        subject=body.get("subject", ""),
        content=body.get("content", ""),
        department=body.get("department"),
    )
    return msg


@app.get("/v1/superadmin/bus/inbox/{agent_id}")
async def bus_inbox(agent_id: str, request: Request, unread: bool = False):
    _verify_superadmin(request)
    return {"messages": agent_bus.get_inbox(agent_id, unread_only=unread)}


@app.get("/v1/superadmin/bus/sent/{agent_id}")
async def bus_sent(agent_id: str, request: Request):
    _verify_superadmin(request)
    return {"messages": agent_bus.get_sent(agent_id)}


@app.get("/v1/superadmin/bus/thread/{message_id}")
async def bus_thread(message_id: str, request: Request):
    _verify_superadmin(request)
    return {"thread": agent_bus.get_thread(message_id)}


@app.post("/v1/superadmin/bus/read/{message_id}")
async def bus_mark_read(message_id: str, request: Request):
    _verify_superadmin(request)
    agent_bus.mark_read(message_id)
    return {"status": "read"}


@app.get("/v1/superadmin/bus/stats")
async def bus_stats(request: Request):
    _verify_superadmin(request)
    return agent_bus.get_stats()


@app.get("/v1/superadmin/bus/messages")
async def bus_all_messages(request: Request, msg_type: str = None, limit: int = 100):
    _verify_superadmin(request)
    return {"messages": agent_bus.get_all_messages(msg_type, limit)}


# ── SuperAdmin: Audit Log ─────────────────────────────

@app.get("/v1/superadmin/audit")
async def get_audit_log(request: Request, entity_type: str = None, limit: int = 100):
    _verify_superadmin(request)
    return {"log": persistence_store.get_audit_log(entity_type, limit)}


# ── SuperAdmin: Unified Agent Registry ─────────────────

@app.get("/v1/superadmin/registry/all")
async def get_unified_registry(request: Request):
    """Get all agents — both monitoring (AGT-*) and team (CDB-*)."""
    _verify_superadmin(request)
    return {
        "agents": agent_registry.get_all_agents(),
        "summary": agent_registry.get_summary(),
    }


# ── SuperAdmin: Department Budget Tracking ─────────

@app.get("/v1/superadmin/budgets")
async def get_department_budgets(request: Request):
    """Track LLM costs per department and agent."""
    _verify_superadmin(request)

    # Load budget config or defaults
    budgets = persistence_store.kv_get("department_budgets", {
        "EXEC": {"monthly_limit": 50.0}, "ENG": {"monthly_limit": 200.0},
        "QA": {"monthly_limit": 100.0}, "OPS": {"monthly_limit": 100.0},
        "SEC": {"monthly_limit": 75.0}, "DOC": {"monthly_limit": 75.0},
    })

    # Calculate spending from LLM request stats
    agents = agent_team.get_all_agents()
    all_tasks = agent_team.get_all_tasks()

    dept_spending = {}
    for dept in ["EXEC", "ENG", "QA", "OPS", "SEC", "DOC"]:
        dept_agents = [a for a in agents if a.get("department") == dept]
        dept_agent_ids = {a["agent_id"] for a in dept_agents}
        dept_tasks = [t for t in all_tasks if t.get("assigned_to") in dept_agent_ids and t.get("status") in ("completed", "review")]
        total_ms = sum(t.get("metadata", {}).get("elapsed_ms", 0) for t in dept_tasks)
        # Estimate cost: ~$0.003 per 1000 tokens, ~1 token per 4 chars, ~500 tokens avg per task
        estimated_cost = len(dept_tasks) * 0.0015
        config = budgets.get(dept, {"monthly_limit": 100.0})
        dept_spending[dept] = {
            "monthly_limit": config["monthly_limit"],
            "spent": round(estimated_cost, 4),
            "remaining": round(config["monthly_limit"] - estimated_cost, 4),
            "usage_pct": round(estimated_cost / config["monthly_limit"] * 100, 1) if config["monthly_limit"] > 0 else 0,
            "task_count": len(dept_tasks),
            "total_elapsed_ms": round(total_ms, 1),
            "agent_count": len(dept_agents),
        }

    return {"departments": dept_spending, "budgets": budgets}

@app.put("/v1/superadmin/budgets")
async def update_department_budgets(request: Request):
    """Update department budget limits."""
    _verify_superadmin(request)
    body = await request.json()
    budgets = persistence_store.kv_get("department_budgets", {})
    for dept, config in body.items():
        budgets[dept] = {**budgets.get(dept, {}), **config}
    persistence_store.kv_set("department_budgets", budgets)
    persistence_store.audit("budget_update", "system", "departments", body)
    return {"status": "updated", "budgets": budgets}


# ── SuperAdmin: Agent Performance Dashboard ────────

@app.get("/v1/superadmin/performance")
async def get_performance_dashboard(request: Request):
    """Agent performance metrics: completion rates, average times, department stats."""
    _verify_superadmin(request)
    agents = agent_team.get_all_agents()
    all_tasks = agent_team.get_all_tasks()

    # Per-agent stats
    agent_stats = []
    for a in agents:
        aid = a["agent_id"]
        my_tasks = [t for t in all_tasks if t.get("assigned_to") == aid]
        completed = [t for t in my_tasks if t.get("status") == "completed"]
        failed = [t for t in my_tasks if t.get("status") == "failed"]
        in_progress = [t for t in my_tasks if t.get("status") == "in_progress"]
        elapsed_times = [
            t.get("metadata", {}).get("elapsed_ms", 0) for t in completed
            if t.get("metadata", {}).get("elapsed_ms")
        ]
        agent_stats.append({
            "agent_id": aid,
            "name": a.get("name", ""),
            "department": a.get("department", ""),
            "state": a.get("state", ""),
            "total_tasks": len(my_tasks),
            "completed": len(completed),
            "failed": len(failed),
            "in_progress": len(in_progress),
            "completion_rate": round(len(completed) / len(my_tasks) * 100, 1) if my_tasks else 0,
            "avg_elapsed_ms": round(sum(elapsed_times) / len(elapsed_times), 1) if elapsed_times else 0,
            "tasks_completed_lifetime": a.get("tasks_completed", 0),
            "tasks_failed_lifetime": a.get("tasks_failed", 0),
        })

    # Department rollup
    dept_stats = {}
    for a in agent_stats:
        dept = a["department"]
        if dept not in dept_stats:
            dept_stats[dept] = {"agents": 0, "total_tasks": 0, "completed": 0, "failed": 0}
        dept_stats[dept]["agents"] += 1
        dept_stats[dept]["total_tasks"] += a["total_tasks"]
        dept_stats[dept]["completed"] += a["completed"]
        dept_stats[dept]["failed"] += a["failed"]

    # Global summary
    total_tasks = len(all_tasks)
    completed_tasks = sum(1 for t in all_tasks if t.get("status") == "completed")

    return {
        "summary": {
            "total_agents": len(agents),
            "total_tasks": total_tasks,
            "completed_tasks": completed_tasks,
            "completion_rate": round(completed_tasks / total_tasks * 100, 1) if total_tasks else 0,
            "active_agents": sum(1 for a in agents if a.get("state") in ("active", "working")),
        },
        "agents": sorted(agent_stats, key=lambda x: x["completed"], reverse=True),
        "departments": dept_stats,
    }


# ── SuperAdmin: Prompt Evolution ───────────────────

@app.get("/v1/superadmin/learning/prompts/performance")
async def get_prompt_performance(request: Request, agent_id: str = None):
    _verify_superadmin(request)
    return prompt_evolution.get_prompt_performance(agent_id)

@app.get("/v1/superadmin/learning/prompts/evolutions")
async def get_prompt_evolutions(request: Request, agent_id: str = None, limit: int = 20):
    _verify_superadmin(request)
    return {"evolutions": prompt_evolution.get_evolutions(agent_id, limit)}

@app.post("/v1/superadmin/learning/prompts/evolve/{agent_id}")
async def evolve_agent_prompt(agent_id: str, request: Request):
    """Generate an evolved system prompt for an agent based on performance data."""
    _verify_superadmin(request)
    agent_data = agent_team.get_agent(agent_id)
    if not agent_data:
        raise HTTPException(404, "Agent not found")
    body = await request.json() if request.headers.get("content-length", "0") != "0" else {}
    provider = body.get("provider", "ollama")
    evolution = await prompt_evolution.evolve_prompt(agent_id, agent_data, provider)
    if not evolution:
        return {"message": "Not enough data to evolve prompt (need 3+ graded tasks)"}
    return evolution

@app.post("/v1/superadmin/learning/prompts/apply/{agent_id}")
async def apply_evolved_prompt(agent_id: str, request: Request):
    """Apply a previously generated evolved prompt to an agent."""
    _verify_superadmin(request)
    body = await request.json()
    new_prompt = body.get("prompt", "")
    if not new_prompt:
        raise HTTPException(400, "No prompt provided")
    success = prompt_evolution.apply_evolution(agent_id, new_prompt, agent_team)
    return {"applied": success}

@app.get("/v1/superadmin/learning/prompts/weak/{agent_id}")
async def get_weak_categories(agent_id: str, request: Request):
    _verify_superadmin(request)
    return {"weak_categories": prompt_evolution.get_weak_categories(agent_id)}


# ── SuperAdmin: Model Performance Tracker ──────────

@app.get("/v1/superadmin/learning/models")
async def get_model_performance(request: Request):
    _verify_superadmin(request)
    return model_tracker.get_performance_data()

@app.get("/v1/superadmin/learning/models/recommend/{category}")
async def get_model_recommendation(category: str, request: Request):
    _verify_superadmin(request)
    rec = model_tracker.recommend(category)
    return rec or {"message": f"No recommendation yet for '{category}' — need more data"}

@app.get("/v1/superadmin/learning/models/recommendations")
async def get_all_recommendations(request: Request):
    _verify_superadmin(request)
    return model_tracker.get_all_recommendations()


# ── SuperAdmin: Outcome Analyzer / Learning Loop ───

@app.get("/v1/superadmin/learning/insights")
async def get_learning_insights(request: Request):
    _verify_superadmin(request)
    return outcome_analyzer.get_insights()

@app.get("/v1/superadmin/learning/analyses")
async def get_recent_analyses(request: Request, limit: int = 20):
    _verify_superadmin(request)
    return {"analyses": outcome_analyzer.get_recent_analyses(limit)}

@app.get("/v1/superadmin/learning/scores")
async def get_quality_scores(request: Request):
    _verify_superadmin(request)
    return outcome_analyzer.get_all_scores()

@app.get("/v1/superadmin/learning/agents/{agent_id}/scores")
async def get_agent_quality_scores(agent_id: str, request: Request):
    _verify_superadmin(request)
    return outcome_analyzer.get_agent_scores(agent_id)

@app.post("/v1/superadmin/learning/analyze/{task_id}")
async def manually_analyze_task(task_id: str, request: Request):
    """Manually trigger outcome analysis for a completed task."""
    _verify_superadmin(request)
    task = agent_team.get_task(task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    if not task.get("result"):
        raise HTTPException(400, "Task has no result to analyze")
    analysis = await outcome_analyzer.analyze(task, task["result"], task.get("assigned_to"))
    return analysis


# ── SuperAdmin: Agent Sleep Cycle ──────────────────

@app.get("/v1/superadmin/learning/sleep-cycle/status")
async def get_sleep_cycle_status(request: Request):
    """Get agent sleep cycle status and history."""
    _verify_superadmin(request)
    if not agent_sleep_cycle:
        return {"error": "Sleep cycle not initialized"}
    return agent_sleep_cycle.get_status()

@app.post("/v1/superadmin/learning/sleep-cycle/run")
async def trigger_sleep_cycle(request: Request):
    """Manually trigger an agent sleep cycle."""
    _verify_superadmin(request)
    if not agent_sleep_cycle:
        raise HTTPException(503, "Sleep cycle not initialized")
    result = await agent_sleep_cycle.run()
    return result


# ── SuperAdmin: Agent Memory ───────────────────────

@app.get("/v1/superadmin/agents/{agent_id}/memory")
async def get_agent_memory(agent_id: str, request: Request):
    _verify_superadmin(request)
    return agent_memory.get_memory_stats(agent_id)

@app.get("/v1/superadmin/agents/{agent_id}/memory/context")
async def get_agent_context(agent_id: str, request: Request):
    _verify_superadmin(request)
    return {"context": agent_memory.build_context(agent_id)}

@app.post("/v1/superadmin/agents/{agent_id}/memory/remember")
async def agent_remember(agent_id: str, request: Request):
    _verify_superadmin(request)
    body = await request.json()
    agent_memory.remember(agent_id, body.get("fact", ""), body.get("category", "general"))
    return {"status": "remembered"}

@app.get("/v1/superadmin/agents/{agent_id}/memory/recall")
async def agent_recall(agent_id: str, request: Request, category: str = None):
    _verify_superadmin(request)
    return {"facts": agent_memory.recall(agent_id, category)}

@app.get("/v1/superadmin/agents/{agent_id}/memory/history")
async def agent_task_history(agent_id: str, request: Request, limit: int = 10):
    _verify_superadmin(request)
    return {"history": agent_memory.get_task_history(agent_id, limit)}

@app.delete("/v1/superadmin/agents/{agent_id}/memory/short-term")
async def clear_agent_short_term(agent_id: str, request: Request):
    _verify_superadmin(request)
    agent_memory.clear_short_term(agent_id)
    return {"status": "cleared"}


# ── SuperAdmin: Engine Bridge ──────────────────────

@app.get("/v1/superadmin/bridge/status")
async def get_bridge_status(request: Request):
    """Get engine bridge connection status."""
    _verify_superadmin(request)
    return engine_bridge.get_status() if engine_bridge else {"error": "Not initialized"}

@app.post("/v1/superadmin/bridge/memory/store")
async def bridge_store_memory(request: Request):
    """Store a fact as a semantic vector in VectorCore."""
    _verify_superadmin(request)
    body = await request.json()
    point_id = await engine_bridge.store_memory_vector(
        body["agent_id"], body["fact"], body.get("category", "general"))
    return {"stored": bool(point_id), "point_id": point_id}

@app.get("/v1/superadmin/bridge/memory/recall/{agent_id}")
async def bridge_recall_memory(agent_id: str, request: Request, query: str = "", limit: int = 5):
    """Semantic recall from VectorCore for an agent."""
    _verify_superadmin(request)
    results = await engine_bridge.recall_similar(agent_id, query, limit=limit)
    return {"results": results, "engine": "VectorCore"}

@app.get("/v1/superadmin/bridge/memory/search")
async def bridge_global_search(request: Request, query: str = "", limit: int = 10):
    """Global semantic search across all agent memories."""
    _verify_superadmin(request)
    results = await engine_bridge.recall_global(query, limit=limit)
    return {"results": results}

@app.get("/v1/superadmin/bridge/events")
async def bridge_read_events(request: Request, last_id: str = "0", count: int = 20):
    """Read recent events from StreamCore."""
    _verify_superadmin(request)
    events = await engine_bridge.read_events(last_id=last_id, count=count)
    return {"events": events, "engine": "StreamCore"}

@app.get("/v1/superadmin/bridge/audit/verify")
async def bridge_verify_audit(request: Request):
    """Verify the immutable audit chain integrity."""
    _verify_superadmin(request)
    result = await engine_bridge.verify_audit_chain()
    return result


# ── SuperAdmin: Cost Tracking ──────────────────────

@app.get("/v1/superadmin/costs")
async def get_cost_totals(request: Request):
    """Get global LLM cost totals."""
    _verify_superadmin(request)
    return cost_tracker.get_totals() if cost_tracker else {"error": "Not initialized"}

@app.get("/v1/superadmin/costs/recent")
async def get_recent_costs(request: Request, limit: int = 50):
    """Get recent cost entries."""
    _verify_superadmin(request)
    return {"entries": cost_tracker.get_recent(limit)}

@app.get("/v1/superadmin/costs/agent/{agent_id}")
async def get_agent_costs(agent_id: str, request: Request):
    """Get cost breakdown for a specific agent."""
    _verify_superadmin(request)
    return cost_tracker.get_agent_costs(agent_id)

@app.get("/v1/superadmin/costs/departments")
async def get_department_costs(request: Request):
    """Get cost breakdown by department."""
    _verify_superadmin(request)
    return {"departments": cost_tracker.get_department_costs()}

@app.get("/v1/superadmin/costs/pricing")
async def get_pricing_table(request: Request):
    """Get the current model pricing table."""
    _verify_superadmin(request)
    return {"pricing": cost_tracker.get_pricing_table()}


# ── SuperAdmin: Agent Chat ─────────────────────────

@app.post("/v1/superadmin/chat/{agent_id}")
async def chat_with_agent(agent_id: str, request: Request):
    """Send a message to an agent and get a response."""
    _verify_superadmin(request)
    body = await request.json()
    message = body.get("message", "")
    if not message:
        raise HTTPException(400, "message is required")
    result = await agent_chat.send_message(agent_id, message, body.get("session_id"))
    return result

@app.post("/v1/superadmin/chat/{agent_id}/stream")
async def stream_chat_with_agent(agent_id: str, request: Request):
    """Stream a response from an agent (SSE)."""
    _verify_superadmin(request)
    body = await request.json()
    message = body.get("message", "")
    if not message:
        raise HTTPException(400, "message is required")

    from starlette.responses import StreamingResponse

    async def generate():
        async for chunk in agent_chat.stream_message(agent_id, message):
            yield f"data: {chunk}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")

@app.get("/v1/superadmin/chat/sessions")
async def get_chat_sessions(request: Request):
    """Get active chat sessions."""
    _verify_superadmin(request)
    return {"sessions": agent_chat.get_sessions()}

@app.delete("/v1/superadmin/chat/{agent_id}/clear")
async def clear_chat(agent_id: str, request: Request):
    """Clear conversation history for an agent."""
    _verify_superadmin(request)
    agent_chat.clear_session(agent_id)
    return {"status": "cleared"}


# ── SuperAdmin: Multi-Agent Collaboration ──────────

@app.post("/v1/superadmin/collab/sessions")
async def create_collab_session(request: Request):
    """Create a new multi-agent collaboration session."""
    _verify_superadmin(request)
    body = await request.json()
    goal = body.get("goal", "")
    agent_ids = body.get("agent_ids", [])
    if not goal or len(agent_ids) < 2:
        raise HTTPException(400, "goal and at least 2 agent_ids required")
    result = collab_manager.create_session(goal, agent_ids, body.get("coordinator_id"))
    return result

@app.post("/v1/superadmin/collab/{session_id}/run")
async def run_collab_round(session_id: str, request: Request):
    """Run one or more rounds of collaboration."""
    _verify_superadmin(request)
    body = await request.json() if request.headers.get("content-length", "0") != "0" else {}
    rounds = body.get("rounds", 1)
    result = await collab_manager.run_round(session_id, rounds=rounds)
    return result

@app.post("/v1/superadmin/collab/{session_id}/synthesize")
async def synthesize_collab(session_id: str, request: Request):
    """Synthesize all contributions into a final output."""
    _verify_superadmin(request)
    result = await collab_manager.synthesize(session_id)
    return result

@app.post("/v1/superadmin/collab/{session_id}/message")
async def add_collab_message(session_id: str, request: Request):
    """Manually inject a message into a collaboration session."""
    _verify_superadmin(request)
    body = await request.json()
    result = await collab_manager.add_message(
        session_id, body.get("agent_id", ""), body.get("message", ""))
    return result

@app.get("/v1/superadmin/collab/sessions")
async def list_collab_sessions(request: Request, status: str = None):
    """List all collaboration sessions."""
    _verify_superadmin(request)
    return {"sessions": collab_manager.get_all_sessions(status)}

@app.get("/v1/superadmin/collab/{session_id}")
async def get_collab_session(session_id: str, request: Request):
    """Get a collaboration session by ID."""
    _verify_superadmin(request)
    session = collab_manager.get_session(session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    return session

@app.post("/v1/superadmin/collab/{session_id}/close")
async def close_collab_session(session_id: str, request: Request):
    """Close a collaboration session."""
    _verify_superadmin(request)
    return collab_manager.close_session(session_id)


# ── SuperAdmin: LLM Rate Limiting ──────────────────

@app.get("/v1/superadmin/rate-limits")
async def get_rate_limits(request: Request):
    _verify_superadmin(request)
    return {"budgets": llm_rate_limiter.get_budgets(), "usage": llm_rate_limiter.get_usage_summary()}

@app.post("/v1/superadmin/rate-limits/budget")
async def set_rate_limit_budget(request: Request):
    _verify_superadmin(request)
    body = await request.json()
    llm_rate_limiter.set_budget(body["key"], body["tokens"])
    return {"status": "updated", "budgets": llm_rate_limiter.get_budgets()}

@app.get("/v1/superadmin/rate-limits/check/{agent_id}")
async def check_rate_limit(agent_id: str, request: Request, department: str = None):
    _verify_superadmin(request)
    return llm_rate_limiter.check(agent_id, department)


# ── SuperAdmin: Agent Tools ────────────────────────

@app.get("/v1/superadmin/tools")
async def get_agent_tools(request: Request):
    _verify_superadmin(request)
    return {"tools": agent_tools.get_tools()}

@app.get("/v1/superadmin/tools/log")
async def get_tool_log(request: Request, agent_id: str = None, limit: int = 20):
    _verify_superadmin(request)
    return {"log": agent_tools.get_execution_log(agent_id, limit)}

@app.post("/v1/superadmin/tools/execute")
async def execute_tool(request: Request):
    """Execute tool calls found in text."""
    _verify_superadmin(request)
    body = await request.json()
    results = await agent_tools.execute_tool_calls(body.get("agent_id", ""), body.get("text", ""))
    return {"results": results}


# ── SuperAdmin: Workflows ──────────────────────────

@app.post("/v1/superadmin/workflows")
async def create_workflow(request: Request):
    _verify_superadmin(request)
    body = await request.json()
    return workflow_engine.create_workflow(body["name"], body.get("description", ""), body.get("steps", []))

@app.post("/v1/superadmin/workflows/{workflow_id}/execute")
async def execute_workflow(workflow_id: str, request: Request):
    _verify_superadmin(request)
    return await workflow_engine.execute(workflow_id)

@app.get("/v1/superadmin/workflows")
async def list_workflows(request: Request):
    _verify_superadmin(request)
    return {"workflows": workflow_engine.get_all_workflows()}

@app.get("/v1/superadmin/workflows/{workflow_id}")
async def get_workflow(workflow_id: str, request: Request):
    _verify_superadmin(request)
    wf = workflow_engine.get_workflow(workflow_id)
    if not wf:
        raise HTTPException(404, "Workflow not found")
    return wf


# ── SuperAdmin: RAG Pipeline ──────────────────────

@app.post("/v1/superadmin/rag/ingest")
async def rag_ingest(request: Request):
    _verify_superadmin(request)
    body = await request.json()
    return await rag_pipeline.ingest(body["title"], body["content"], body.get("source", "manual"))

@app.get("/v1/superadmin/rag/retrieve")
async def rag_retrieve(request: Request, query: str = "", limit: int = 5):
    _verify_superadmin(request)
    chunks = await rag_pipeline.retrieve(query, limit=limit)
    return {"chunks": chunks, "context": rag_pipeline.build_rag_context(chunks)}

@app.get("/v1/superadmin/rag/documents")
async def rag_documents(request: Request):
    _verify_superadmin(request)
    return {"documents": rag_pipeline.get_documents()}

@app.delete("/v1/superadmin/rag/documents/{doc_id}")
async def rag_delete(doc_id: str, request: Request):
    _verify_superadmin(request)
    return rag_pipeline.delete_document(doc_id)

@app.get("/v1/superadmin/rag/stats")
async def rag_stats(request: Request):
    _verify_superadmin(request)
    return rag_pipeline.get_stats()


# ── SuperAdmin: Agent Templates ────────────────────

@app.get("/v1/superadmin/templates")
async def get_templates(request: Request):
    _verify_superadmin(request)
    return {"templates": template_manager.get_templates()}

@app.post("/v1/superadmin/templates")
async def create_template(request: Request):
    _verify_superadmin(request)
    body = await request.json()
    return template_manager.create_template(
        body["name"], body["title"], body["department"],
        body.get("skills", []), body.get("system_prompt", ""),
        body.get("llm_provider", "ollama"), body.get("category", "general"))

@app.post("/v1/superadmin/templates/{template_id}/spawn")
async def spawn_from_template(template_id: str, request: Request):
    _verify_superadmin(request)
    body = await request.json() if request.headers.get("content-length", "0") != "0" else {}
    return template_manager.spawn_from_template(template_id, body.get("name"))

@app.post("/v1/superadmin/agents/{agent_id}/clone")
async def clone_agent_endpoint(agent_id: str, request: Request):
    _verify_superadmin(request)
    body = await request.json() if request.headers.get("content-length", "0") != "0" else {}
    return template_manager.clone_agent(agent_id, body.get("name"))


# ── SuperAdmin: Agent Scheduler ────────────────────

@app.get("/v1/superadmin/scheduler/status")
async def get_scheduler_status(request: Request):
    _verify_superadmin(request)
    return agent_scheduler.get_status()

@app.get("/v1/superadmin/scheduler/jobs")
async def get_scheduled_jobs(request: Request, agent_id: str = None):
    _verify_superadmin(request)
    return {"jobs": agent_scheduler.get_jobs(agent_id)}

@app.post("/v1/superadmin/scheduler/jobs")
async def create_scheduled_job(request: Request):
    _verify_superadmin(request)
    body = await request.json()
    return agent_scheduler.create_job(
        body["agent_id"], body["title"], body["prompt"],
        body.get("interval", "daily"), body.get("category", "general"))

@app.put("/v1/superadmin/scheduler/jobs/{job_id}")
async def update_scheduled_job(job_id: str, request: Request):
    _verify_superadmin(request)
    body = await request.json()
    return agent_scheduler.update_job(job_id, body)

@app.delete("/v1/superadmin/scheduler/jobs/{job_id}")
async def delete_scheduled_job(job_id: str, request: Request):
    _verify_superadmin(request)
    return agent_scheduler.delete_job(job_id)


# ── SuperAdmin: Unified Health ─────────────────────

@app.get("/v1/superadmin/health/unified")
async def unified_health(request: Request):
    """Unified health check across all engines, agents, and LLM providers."""
    _verify_superadmin(request)
    health = {"timestamp": time.time(), "engines": {}, "llm": {}, "agents": {}, "services": {}}

    # Core engines
    if db:
        for name, engine in db.engines.items():
            try:
                h = await engine.health()
                health["engines"][name] = {"status": "healthy", **h}
            except Exception as e:
                health["engines"][name] = {"status": "unhealthy", "error": str(e)}

    # LLM providers
    health["llm"] = llm_router.get_providers_status() if llm_router else {}

    # Agent stats
    if agent_team:
        agents = agent_team.get_all_agents()
        by_state = {}
        for a in agents:
            state = a.get("state", "unknown")
            by_state[state] = by_state.get(state, 0) + 1
        health["agents"] = {"total": len(agents), "by_state": by_state}

    # Services
    health["services"]["task_executor"] = task_executor.get_status() if task_executor else {}
    health["services"]["sleep_cycle"] = agent_sleep_cycle.get_status() if agent_sleep_cycle else {}
    health["services"]["scheduler"] = agent_scheduler.get_status() if agent_scheduler else {}
    health["services"]["engine_bridge"] = engine_bridge.get_status() if engine_bridge else {}
    health["services"]["rag"] = rag_pipeline.get_stats() if rag_pipeline else {}

    return health


# ── SuperAdmin: Schema Migrations ──────────────────

@app.get("/v1/superadmin/migrations")
async def get_migrations(request: Request):
    _verify_superadmin(request)
    from cortexdb.superadmin.migrations import MigrationRunner, MIGRATIONS
    runner = MigrationRunner(persistence_store.conn)
    return {
        "current_version": runner.get_current_version(),
        "pending": [{"version": m.version, "description": m.description} for m in runner.get_pending()],
        "history": runner.get_history(),
        "total_available": len(MIGRATIONS),
    }

@app.post("/v1/superadmin/migrations/run")
async def run_migrations(request: Request):
    _verify_superadmin(request)
    from cortexdb.superadmin.migrations import MigrationRunner
    runner = MigrationRunner(persistence_store.conn)
    applied = runner.migrate()
    persistence_store.audit("schema_migration", "system", str(runner.get_current_version()),
                            {"applied": applied})
    return {"applied": applied, "current_version": runner.get_current_version()}


# ── SuperAdmin: Version Management ─────────────────

@app.get("/v1/superadmin/version")
async def get_version_info(request: Request):
    _verify_superadmin(request)
    from cortexdb.version import get_version, CHANGELOG_FILE
    changelog_exists = CHANGELOG_FILE.exists()
    return {
        "version": get_version(),
        "has_changelog": changelog_exists,
    }

@app.post("/v1/superadmin/version/bump")
async def bump_version_endpoint(request: Request):
    _verify_superadmin(request)
    from cortexdb.version import bump_version
    body = await request.json()
    bump_type = body.get("bump", "patch")
    reason = body.get("reason", "")
    changes = body.get("changes", [])
    if bump_type not in ("major", "minor", "patch"):
        return {"error": "bump must be major, minor, or patch"}
    new_version = bump_version(bump_type, reason, changes)
    persistence_store.audit("version_bump", "system", new_version,
                            {"bump": bump_type, "reason": reason, "changes": changes})
    return {"version": new_version, "bump": bump_type}

@app.get("/v1/superadmin/version/changelog")
async def get_changelog_endpoint(request: Request, limit: int = 10):
    _verify_superadmin(request)
    from cortexdb.version import get_changelog
    return {"changelog": get_changelog(limit)}

@app.post("/v1/superadmin/version/sync")
async def sync_version_endpoint(request: Request):
    _verify_superadmin(request)
    from cortexdb.version import sync_all, get_version
    count = sync_all()
    return {"version": get_version(), "files_synced": count}


# ── SuperAdmin: Agent Skills ──────────────────────────

@app.get("/v1/superadmin/skills/{agent_id}")
async def get_agent_skill_profile(agent_id: str, request: Request):
    """Get full structured skill profile for an agent."""
    _verify_superadmin(request)
    return skill_manager.get_profile(agent_id)

@app.get("/v1/superadmin/skills")
async def get_all_skill_profiles(request: Request):
    """Get skill profile summaries for all agents."""
    _verify_superadmin(request)
    return {"profiles": skill_manager.get_all_profiles_summary()}

@app.get("/v1/superadmin/skills/catalog")
async def get_skill_catalog(request: Request):
    """Get all known skills across the organization."""
    _verify_superadmin(request)
    return skill_manager.get_skill_catalog()

@app.get("/v1/superadmin/skills/leaderboard")
async def get_skill_leaderboard(request: Request, skill: str = None):
    """Get agents ranked by skill XP."""
    _verify_superadmin(request)
    return {"leaderboard": skill_manager.get_skill_leaderboard(skill)}

@app.get("/v1/superadmin/skills/{agent_id}/history")
async def get_skill_history(agent_id: str, request: Request):
    """Get recent skill enhancement events for an agent."""
    _verify_superadmin(request)
    return {"history": skill_manager.get_enhancement_history(agent_id)}

@app.post("/v1/superadmin/skills/{agent_id}")
async def add_agent_skill(agent_id: str, request: Request):
    """Manually add a skill to an agent."""
    _verify_superadmin(request)
    body = await request.json()
    skill_name = body.get("skill_name", "").strip()
    if not skill_name:
        raise HTTPException(400, "skill_name required")
    result = skill_manager.add_skill(
        agent_id, skill_name,
        category=body.get("category"),
        level=body.get("level", 1),
    )
    if "error" in result:
        raise HTTPException(400, result["error"])
    return result

@app.delete("/v1/superadmin/skills/{agent_id}/{skill_name}")
async def remove_agent_skill(agent_id: str, skill_name: str, request: Request):
    """Remove a skill from an agent."""
    _verify_superadmin(request)
    result = skill_manager.remove_skill(agent_id, skill_name)
    if "error" in result:
        raise HTTPException(404, result["error"])
    return result

@app.post("/v1/superadmin/skills/{agent_id}/enhance")
async def manually_enhance_skills(agent_id: str, request: Request):
    """Manually trigger skill enhancement (simulates a task outcome)."""
    _verify_superadmin(request)
    body = await request.json()
    category = body.get("category", "general")
    grade = max(1, min(10, body.get("grade", 7)))
    keywords = body.get("keywords", [])
    changes = skill_manager.enhance_from_outcome(agent_id, category, grade, keywords)
    skill_manager.record_enhancement(agent_id, changes)
    return {"changes": changes, "profile": skill_manager.get_profile(agent_id)}


# ── SuperAdmin: Agent Reputation ──────────────────────────

@app.get("/v1/superadmin/reputation/{agent_id}")
async def get_agent_reputation(agent_id: str, request: Request):
    _verify_superadmin(request)
    return agent_reputation.get_trust_score(agent_id)

@app.get("/v1/superadmin/reputation")
async def get_all_reputations(request: Request):
    _verify_superadmin(request)
    return {"scores": agent_reputation.get_all_scores()}

@app.post("/v1/superadmin/reputation/{agent_id}/update")
async def update_reputation(agent_id: str, request: Request):
    _verify_superadmin(request)
    body = await request.json()
    if "grade" in body:
        agent_reputation.update_from_outcome(agent_id, body["grade"])
    if "delegation_success" in body:
        agent_reputation.update_from_delegation(agent_id, body["delegation_success"])
    return agent_reputation.get_trust_score(agent_id)

@app.get("/v1/superadmin/reputation/{agent_id}/can-delegate")
async def check_can_delegate(agent_id: str, request: Request):
    _verify_superadmin(request)
    return {"agent_id": agent_id, "can_delegate": agent_reputation.can_delegate(agent_id)}


# ── SuperAdmin: Agent Delegation ──────────────────────────

@app.get("/v1/superadmin/delegation/candidates/{task_id}")
async def get_delegation_candidates(task_id: str, request: Request):
    _verify_superadmin(request)
    limit = int(request.query_params.get("limit", "5"))
    return {"candidates": agent_delegation.find_candidates(task_id, limit=limit)}

@app.post("/v1/superadmin/delegation/delegate")
async def delegate_task(request: Request):
    _verify_superadmin(request)
    body = await request.json()
    task_id = body.get("task_id")
    from_agent = body.get("from_agent")
    to_agent = body.get("to_agent")
    if not task_id or not from_agent:
        raise HTTPException(400, "task_id and from_agent required")
    result = agent_delegation.delegate(task_id, from_agent, to_agent)
    if "error" in result:
        raise HTTPException(400, result["error"])
    return result

@app.post("/v1/superadmin/delegation/auto")
async def auto_delegate_task(request: Request):
    _verify_superadmin(request)
    body = await request.json()
    task_id = body.get("task_id")
    from_agent = body.get("from_agent")
    if not task_id or not from_agent:
        raise HTTPException(400, "task_id and from_agent required")
    result = agent_delegation.auto_delegate(task_id, from_agent)
    if "error" in result:
        raise HTTPException(400, result["error"])
    return result

@app.get("/v1/superadmin/delegation/log")
async def get_delegation_log(request: Request):
    _verify_superadmin(request)
    limit = int(request.query_params.get("limit", "50"))
    log = persistence_store.kv_get("delegation_log", [])
    return {"delegations": log[-limit:], "total": len(log)}

@app.get("/v1/superadmin/delegation/stats")
async def get_delegation_stats(request: Request):
    _verify_superadmin(request)
    log = persistence_store.kv_get("delegation_log", [])
    success = sum(1 for d in log if d.get("outcome") == "success")
    return {
        "total": len(log),
        "successful": success,
        "failed": len(log) - success,
        "success_rate": round(success / max(len(log), 1), 2),
    }


# ── SuperAdmin: Goal Decomposition ──────────────────────────

@app.post("/v1/superadmin/goals/decompose")
async def decompose_goal(request: Request):
    _verify_superadmin(request)
    body = await request.json()
    goal = body.get("goal", "")
    if not goal:
        raise HTTPException(400, "goal required")
    result = await goal_decomposer.decompose(
        goal, context=body.get("context"), owner=body.get("owner"))
    return result

@app.post("/v1/superadmin/goals/suggest")
async def suggest_goal_plan(request: Request):
    _verify_superadmin(request)
    body = await request.json()
    goal = body.get("goal", "")
    if not goal:
        raise HTTPException(400, "goal required")
    result = await goal_decomposer.suggest(goal, context=body.get("context"))
    return result

@app.get("/v1/superadmin/goals/history")
async def get_goal_history(request: Request):
    _verify_superadmin(request)
    goals = persistence_store.kv_get("goal_decompositions", [])
    return {"goals": goals}

@app.get("/v1/superadmin/goals/{goal_id}")
async def get_goal_detail(goal_id: str, request: Request):
    _verify_superadmin(request)
    goals = persistence_store.kv_get("goal_decompositions", [])
    for g in goals:
        if g.get("goal_id") == goal_id:
            return g
    raise HTTPException(404, "Goal not found")


# ── SuperAdmin: Auto-Hiring ──────────────────────────

@app.get("/v1/superadmin/hiring/gaps")
async def detect_hiring_gaps(request: Request):
    _verify_superadmin(request)
    return {"gaps": auto_hiring.detect_gaps()}

@app.get("/v1/superadmin/hiring/recommendations")
async def get_hiring_recommendations(request: Request):
    _verify_superadmin(request)
    return {"recommendations": auto_hiring.recommend_hires()}

@app.post("/v1/superadmin/hiring/hire")
async def auto_hire_agent(request: Request):
    _verify_superadmin(request)
    body = await request.json()
    template_id = body.get("template_id")
    overrides = body.get("overrides", {})
    if not template_id:
        raise HTTPException(400, "template_id required")
    result = auto_hiring.auto_hire(template_id, overrides)
    if "error" in result:
        raise HTTPException(400, result["error"])
    return result

@app.get("/v1/superadmin/hiring/history")
async def get_hiring_history(request: Request):
    _verify_superadmin(request)
    return {"history": persistence_store.kv_get("hiring_history", [])}

@app.get("/v1/superadmin/hiring/templates")
async def get_hiring_templates(request: Request):
    _verify_superadmin(request)
    if template_manager:
        return {"templates": template_manager.list_templates()}
    return {"templates": []}


# ── SuperAdmin: Sprint Planning ──────────────────────────

@app.post("/v1/superadmin/sprints")
async def create_sprint(request: Request):
    _verify_superadmin(request)
    body = await request.json()
    goal = body.get("goal", "")
    duration_days = body.get("duration_days", 7)
    if not goal:
        raise HTTPException(400, "goal required")
    result = await sprint_planner.plan_sprint(goal, duration_days=duration_days)
    return result

@app.get("/v1/superadmin/sprints")
async def list_sprints(request: Request):
    _verify_superadmin(request)
    return {"sprints": sprint_planner.list_sprints()}

@app.get("/v1/superadmin/sprints/{sprint_id}")
async def get_sprint(sprint_id: str, request: Request):
    _verify_superadmin(request)
    sprint = sprint_planner.get_sprint(sprint_id)
    if not sprint:
        raise HTTPException(404, "Sprint not found")
    return sprint

@app.post("/v1/superadmin/sprints/{sprint_id}/activate")
async def activate_sprint(sprint_id: str, request: Request):
    _verify_superadmin(request)
    result = sprint_planner.activate_sprint(sprint_id)
    if "error" in result:
        raise HTTPException(400, result["error"])
    return result

@app.get("/v1/superadmin/sprints/{sprint_id}/standup")
async def sprint_standup(sprint_id: str, request: Request):
    _verify_superadmin(request)
    result = sprint_planner.standup(sprint_id)
    if "error" in result:
        raise HTTPException(404, result["error"])
    return result

@app.post("/v1/superadmin/sprints/{sprint_id}/complete")
async def complete_sprint(sprint_id: str, request: Request):
    _verify_superadmin(request)
    sprints = persistence_store.kv_get("sprints", [])
    for s in sprints:
        if s.get("sprint_id") == sprint_id:
            s["status"] = "completed"
            s["completed_at"] = time.time()
            persistence_store.kv_set("sprints", sprints)
            return s
    raise HTTPException(404, "Sprint not found")


# ── SuperAdmin: Self-Improvement ──────────────────────────

@app.post("/v1/superadmin/improvement/{agent_id}")
async def generate_improvement_proposal(agent_id: str, request: Request):
    _verify_superadmin(request)
    result = await self_improvement.generate_proposal(agent_id)
    if "error" in result:
        raise HTTPException(400, result["error"])
    return result

@app.post("/v1/superadmin/improvement/all")
async def generate_all_improvement_proposals(request: Request):
    _verify_superadmin(request)
    results = await self_improvement.generate_all()
    return {"proposals": results}

@app.get("/v1/superadmin/improvement/proposals")
async def get_improvement_proposals(request: Request):
    _verify_superadmin(request)
    return {"proposals": persistence_store.kv_get("improvement_proposals", [])}

@app.post("/v1/superadmin/improvement/{proposal_id}/approve")
async def approve_improvement(proposal_id: str, request: Request):
    _verify_superadmin(request)
    result = self_improvement.approve_proposal(proposal_id)
    if "error" in result:
        raise HTTPException(404, result["error"])
    return result

@app.post("/v1/superadmin/improvement/{proposal_id}/reject")
async def reject_improvement(proposal_id: str, request: Request):
    _verify_superadmin(request)
    result = self_improvement.reject_proposal(proposal_id)
    if "error" in result:
        raise HTTPException(404, result["error"])
    return result


# ── SuperAdmin: Alert System ──────────────────────────

@app.get("/v1/superadmin/alerts")
async def get_alerts(request: Request):
    _verify_superadmin(request)
    severity = request.query_params.get("severity")
    unacked = request.query_params.get("unacked", "false").lower() == "true"
    alerts = alert_system.get_alerts(severity=severity, unacked_only=unacked)
    return {"alerts": alerts, "total": len(alerts)}

@app.post("/v1/superadmin/alerts")
async def create_alert(request: Request):
    _verify_superadmin(request)
    body = await request.json()
    alert = alert_system.create_alert(
        alert_type=body.get("type", "custom"),
        severity=body.get("severity", "info"),
        title=body.get("title", ""),
        details=body.get("details", {}),
    )
    return alert

@app.post("/v1/superadmin/alerts/{alert_id}/ack")
async def acknowledge_alert(alert_id: str, request: Request):
    _verify_superadmin(request)
    result = alert_system.acknowledge(alert_id)
    if "error" in result:
        raise HTTPException(404, result["error"])
    return result

@app.post("/v1/superadmin/alerts/ack-all")
async def acknowledge_all_alerts(request: Request):
    _verify_superadmin(request)
    return alert_system.acknowledge_all()

@app.get("/v1/superadmin/alerts/summary")
async def get_alert_summary(request: Request):
    _verify_superadmin(request)
    alerts = alert_system.get_alerts()
    unacked = [a for a in alerts if not a.get("acknowledged")]
    by_severity = {}
    for a in unacked:
        sev = a.get("severity", "info")
        by_severity[sev] = by_severity.get(sev, 0) + 1
    return {
        "total": len(alerts),
        "unacknowledged": len(unacked),
        "by_severity": by_severity,
    }


# ── SuperAdmin: Agent Metrics ──────────────────────────

@app.get("/v1/superadmin/metrics/agent/{agent_id}")
async def get_agent_metrics_endpoint(agent_id: str, request: Request):
    _verify_superadmin(request)
    return agent_metrics_mgr.get_agent_metrics(agent_id)

@app.get("/v1/superadmin/metrics/team")
async def get_team_metrics(request: Request):
    _verify_superadmin(request)
    return agent_metrics_mgr.get_team_metrics()

@app.get("/v1/superadmin/metrics/department/{dept}")
async def get_department_metrics(dept: str, request: Request):
    _verify_superadmin(request)
    return agent_metrics_mgr.get_department_metrics(dept)

@app.get("/v1/superadmin/metrics/summary")
async def get_metrics_summary(request: Request):
    _verify_superadmin(request)
    return agent_metrics_mgr.get_summary()

@app.get("/v1/superadmin/metrics/departments")
async def get_all_department_metrics(request: Request):
    _verify_superadmin(request)
    agents = agent_team.get_all_agents()
    depts = list({a.get("department", "") for a in agents if a.get("department")})
    return {"departments": [agent_metrics_mgr.get_department_metrics(d) for d in sorted(depts)]}


# ── SuperAdmin: Execution Replay ──────────────────────────

@app.get("/v1/superadmin/replay/recent")
async def get_recent_traces(request: Request):
    _verify_superadmin(request)
    limit = int(request.query_params.get("limit", "20"))
    return {"traces": execution_replay.get_recent(limit)}

@app.get("/v1/superadmin/replay/{task_id}")
async def get_execution_trace(task_id: str, request: Request):
    _verify_superadmin(request)
    trace = execution_replay.get_trace(task_id)
    if not trace:
        raise HTTPException(404, "Trace not found")
    return trace

@app.get("/v1/superadmin/replay/stats")
async def get_replay_stats(request: Request):
    _verify_superadmin(request)
    return {"step_stats": execution_replay.get_step_stats()}

@app.get("/v1/superadmin/replay/active")
async def get_active_traces(request: Request):
    _verify_superadmin(request)
    active = {tid: t.to_dict() for tid, t in execution_replay._active_traces.items()}
    return {"active_traces": active, "count": len(active)}


# ── SuperAdmin: Cost Optimizer ──────────────────────────

@app.get("/v1/superadmin/cost-optimizer/report")
async def get_cost_optimization_report(request: Request):
    _verify_superadmin(request)
    return cost_optimizer.get_report()

@app.get("/v1/superadmin/cost-optimizer/recommend/{category}")
async def get_cost_recommendation(category: str, request: Request):
    _verify_superadmin(request)
    threshold = float(request.query_params.get("threshold", "6.0"))
    rec = cost_optimizer.recommend(category, quality_threshold=threshold)
    if not rec:
        return {"category": category, "recommendation": None, "message": "No qualifying models found"}
    return {"category": category, "recommendation": rec}

@app.post("/v1/superadmin/cost-optimizer/apply")
async def apply_cost_optimizations(request: Request):
    _verify_superadmin(request)
    body = await request.json()
    dry_run = body.get("dry_run", True)
    return cost_optimizer.apply_optimizations(dry_run=dry_run)

@app.get("/v1/superadmin/cost-optimizer/providers")
async def get_provider_costs(request: Request):
    _verify_superadmin(request)
    from cortexdb.superadmin.cost_optimizer import PROVIDER_COSTS
    return {"providers": PROVIDER_COSTS}

@app.get("/v1/superadmin/cost-optimizer/savings")
async def get_potential_savings(request: Request):
    _verify_superadmin(request)
    report = cost_optimizer.get_report()
    return {
        "current_cost": report["current_total_cost"],
        "potential_savings": report["potential_savings"],
        "savings_pct": round(report["potential_savings"] / max(report["current_total_cost"], 0.01) * 100, 1),
    }


# ── SuperAdmin: Compliance Reports ──────────────────────────

@app.get("/v1/superadmin/reports/types")
async def get_report_types(request: Request):
    _verify_superadmin(request)
    return {"types": compliance_reporter.get_types()}

@app.post("/v1/superadmin/reports/generate")
async def generate_compliance_report(request: Request):
    _verify_superadmin(request)
    body = await request.json()
    report_type = body.get("report_type", "")
    if not report_type:
        raise HTTPException(400, "report_type required")
    report = compliance_reporter.generate(
        report_type, from_date=body.get("from_date"), to_date=body.get("to_date"))
    if "error" in report:
        raise HTTPException(400, report["error"])
    return report

@app.get("/v1/superadmin/reports")
async def list_compliance_reports(request: Request):
    _verify_superadmin(request)
    return {"reports": compliance_reporter.get_reports()}

@app.get("/v1/superadmin/reports/{report_id}")
async def get_compliance_report(report_id: str, request: Request):
    _verify_superadmin(request)
    report = compliance_reporter.get_report(report_id)
    if not report:
        raise HTTPException(404, "Report not found")
    return report


# ── SuperAdmin: Live Feed ──────────────────────────

@app.get("/v1/superadmin/live-feed")
async def get_live_feed(request: Request):
    _verify_superadmin(request)
    limit = int(request.query_params.get("limit", "50"))
    events = persistence_store.kv_get("live_feed_events", [])
    return {"events": events[-limit:], "total": len(events)}


# ── SuperAdmin: Knowledge Graph ──────────────────────────

@app.post("/v1/superadmin/knowledge/nodes")
async def create_knowledge_node(request: Request):
    _verify_superadmin(request)
    body = await request.json()
    if not body.get("topic") or not body.get("content"):
        raise HTTPException(400, "topic and content required")
    return knowledge_graph.add_node(
        node_type=body.get("node_type", "insight"), topic=body["topic"],
        content=body["content"], source_agent=body.get("source_agent"),
        department=body.get("department"), confidence=body.get("confidence", 0.5),
        metadata=body.get("metadata"))

@app.get("/v1/superadmin/knowledge/nodes")
async def query_knowledge_nodes(request: Request):
    _verify_superadmin(request)
    return {"nodes": knowledge_graph.query_nodes(
        topic=request.query_params.get("topic"), agent_id=request.query_params.get("agent_id"),
        department=request.query_params.get("department"), node_type=request.query_params.get("node_type"),
        limit=int(request.query_params.get("limit", "50")))}

@app.get("/v1/superadmin/knowledge/nodes/{node_id}")
async def get_knowledge_node(node_id: str, request: Request):
    _verify_superadmin(request)
    node = knowledge_graph.get_node(node_id)
    if not node:
        raise HTTPException(404, "Node not found")
    return node

@app.put("/v1/superadmin/knowledge/nodes/{node_id}")
async def update_knowledge_node(node_id: str, request: Request):
    _verify_superadmin(request)
    body = await request.json()
    return knowledge_graph.update_node(node_id, body)

@app.delete("/v1/superadmin/knowledge/nodes/{node_id}")
async def delete_knowledge_node(node_id: str, request: Request):
    _verify_superadmin(request)
    knowledge_graph.delete_node(node_id)
    return {"deleted": node_id}

@app.post("/v1/superadmin/knowledge/edges")
async def create_knowledge_edge(request: Request):
    _verify_superadmin(request)
    body = await request.json()
    if not body.get("from_node") or not body.get("to_node") or not body.get("relation"):
        raise HTTPException(400, "from_node, to_node, and relation required")
    return knowledge_graph.add_edge(body["from_node"], body["to_node"], body["relation"],
                                     weight=body.get("weight", 1.0), metadata=body.get("metadata"))

@app.delete("/v1/superadmin/knowledge/edges/{edge_id}")
async def delete_knowledge_edge(edge_id: str, request: Request):
    _verify_superadmin(request)
    knowledge_graph.delete_edge(edge_id)
    return {"deleted": edge_id}

@app.get("/v1/superadmin/knowledge/neighbors/{node_id}")
async def get_knowledge_neighbors(node_id: str, request: Request):
    _verify_superadmin(request)
    depth = int(request.query_params.get("depth", "1"))
    return knowledge_graph.get_neighbors(node_id, relation=request.query_params.get("relation"), depth=depth)

@app.get("/v1/superadmin/knowledge/search")
async def search_knowledge(request: Request):
    _verify_superadmin(request)
    query = request.query_params.get("query", "")
    if not query:
        raise HTTPException(400, "query parameter required")
    return {"results": knowledge_graph.search_nodes(query, limit=int(request.query_params.get("limit", "20")))}

@app.get("/v1/superadmin/knowledge/stats")
async def get_knowledge_stats(request: Request):
    _verify_superadmin(request)
    return knowledge_graph.get_stats()


# ── SuperAdmin: Knowledge Propagation ──────────────────────────

@app.post("/v1/superadmin/knowledge/propagate/{node_id}")
async def propagate_knowledge(node_id: str, request: Request):
    _verify_superadmin(request)
    return knowledge_propagator.propagate_insight(node_id)

@app.get("/v1/superadmin/knowledge/propagations/{agent_id}")
async def get_agent_propagations(agent_id: str, request: Request):
    _verify_superadmin(request)
    return {"propagations": knowledge_propagator.get_pending_propagations(agent_id)}

@app.post("/v1/superadmin/knowledge/propagations/{propagation_id}/accept")
async def accept_knowledge_propagation(propagation_id: str, request: Request):
    _verify_superadmin(request)
    body = await request.json()
    return knowledge_propagator.accept_propagation(propagation_id, body.get("agent_id", ""))

@app.post("/v1/superadmin/knowledge/propagations/{propagation_id}/dismiss")
async def dismiss_knowledge_propagation(propagation_id: str, request: Request):
    _verify_superadmin(request)
    return knowledge_propagator.dismiss_propagation(propagation_id)

@app.post("/v1/superadmin/knowledge/propagate-batch")
async def batch_propagate_knowledge(request: Request):
    _verify_superadmin(request)
    body = await request.json()
    return knowledge_propagator.auto_propagate_high_grade(min_confidence=body.get("min_confidence", 0.8))

@app.get("/v1/superadmin/knowledge/propagation-stats")
async def get_propagation_stats(request: Request):
    _verify_superadmin(request)
    return knowledge_propagator.get_propagation_stats()


# ── SuperAdmin: Context Pools ──────────────────────────

@app.post("/v1/superadmin/knowledge/pools/{department}/contribute")
async def contribute_to_pool(department: str, request: Request):
    _verify_superadmin(request)
    body = await request.json()
    if not body.get("content"):
        raise HTTPException(400, "content required")
    return context_pools.contribute(department, body.get("agent_id", "superadmin"),
                                     body["content"], category=body.get("category", "general"))

@app.get("/v1/superadmin/knowledge/pools/{department}")
async def get_context_pool(department: str, request: Request):
    _verify_superadmin(request)
    return context_pools.get_pool(department, category=request.query_params.get("category"),
                                   limit=int(request.query_params.get("limit", "50")))

@app.get("/v1/superadmin/knowledge/pools")
async def list_context_pools(request: Request):
    _verify_superadmin(request)
    return {"pools": context_pools.list_pools()}

@app.get("/v1/superadmin/knowledge/pools/{department}/relevant")
async def get_relevant_context(department: str, request: Request):
    _verify_superadmin(request)
    agent_id = request.query_params.get("agent_id", "")
    task = request.query_params.get("task", "")
    return {"context": context_pools.get_relevant_context(agent_id, task)}

@app.post("/v1/superadmin/knowledge/pools/prune")
async def prune_context_pools(request: Request):
    _verify_superadmin(request)
    body = await request.json()
    return context_pools.prune_stale(max_age_days=body.get("max_age_days", 30))


# ── SuperAdmin: Expert Discovery ──────────────────────────

@app.get("/v1/superadmin/knowledge/experts")
async def find_experts(request: Request):
    _verify_superadmin(request)
    query = request.query_params.get("query", "")
    if not query:
        raise HTTPException(400, "query parameter required")
    return {"experts": expert_discovery.find_expert(query, domain=request.query_params.get("domain"),
                                                     top_k=int(request.query_params.get("top_k", "5")))}

@app.get("/v1/superadmin/knowledge/domain-map")
async def get_domain_map(request: Request):
    _verify_superadmin(request)
    return expert_discovery.get_domain_map()

@app.get("/v1/superadmin/knowledge/recommend")
async def recommend_expert_for_task(request: Request):
    _verify_superadmin(request)
    task = request.query_params.get("task", "")
    if not task:
        raise HTTPException(400, "task parameter required")
    return {"recommendations": expert_discovery.recommend_for_task(task)}

@app.get("/v1/superadmin/knowledge/expertise-matrix")
async def get_expertise_matrix(request: Request):
    _verify_superadmin(request)
    return expert_discovery.get_expertise_matrix(department=request.query_params.get("department"))


# ── SuperAdmin: Simulations ──────────────────────────

@app.post("/v1/superadmin/simulations")
async def create_simulation(request: Request):
    _verify_superadmin(request)
    body = await request.json()
    if not body.get("name") or not body.get("sim_type"):
        raise HTTPException(400, "name and sim_type required")
    return simulation_engine.create_simulation(
        body["name"], body["sim_type"], config=body.get("config"), agent_ids=body.get("agent_ids"))

@app.get("/v1/superadmin/simulations")
async def list_simulations_endpoint(request: Request):
    _verify_superadmin(request)
    return {"simulations": simulation_engine.list_simulations(
        status=request.query_params.get("status"), sim_type=request.query_params.get("sim_type"))}

@app.get("/v1/superadmin/simulations/stats")
async def get_simulation_stats(request: Request):
    _verify_superadmin(request)
    return simulation_engine.get_stats()

@app.get("/v1/superadmin/simulations/{sim_id}")
async def get_simulation_detail(sim_id: str, request: Request):
    _verify_superadmin(request)
    sim = simulation_engine.get_simulation(sim_id)
    if not sim:
        raise HTTPException(404, "Simulation not found")
    return sim

@app.post("/v1/superadmin/simulations/{sim_id}/run")
async def run_simulation_task(sim_id: str, request: Request):
    _verify_superadmin(request)
    body = await request.json()
    if not body.get("task_prompt") or not body.get("agent_id"):
        raise HTTPException(400, "task_prompt and agent_id required")
    return await simulation_engine.run_task_in_sandbox(
        sim_id, body["task_prompt"], body["agent_id"], system_prompt=body.get("system_prompt"))

@app.post("/v1/superadmin/simulations/{sim_id}/stop")
async def stop_simulation(sim_id: str, request: Request):
    _verify_superadmin(request)
    return simulation_engine.update_simulation(sim_id, {"status": "stopped"})

@app.delete("/v1/superadmin/simulations/{sim_id}")
async def cleanup_simulation(sim_id: str, request: Request):
    _verify_superadmin(request)
    return simulation_engine.cleanup_simulation(sim_id)


# ── SuperAdmin: Behavior Tests ──────────────────────────

@app.post("/v1/superadmin/simulations/test-suites")
async def create_test_suite(request: Request):
    _verify_superadmin(request)
    body = await request.json()
    if not body.get("name") or not body.get("test_cases"):
        raise HTTPException(400, "name and test_cases required")
    return behavior_tests.create_suite(body["name"], body.get("description", ""), body["test_cases"])

@app.get("/v1/superadmin/simulations/test-suites")
async def list_test_suites(request: Request):
    _verify_superadmin(request)
    return {"suites": behavior_tests.list_suites()}

@app.get("/v1/superadmin/simulations/test-suites/{suite_id}")
async def get_test_suite(suite_id: str, request: Request):
    _verify_superadmin(request)
    suite = behavior_tests.get_suite(suite_id)
    if not suite:
        raise HTTPException(404, "Suite not found")
    return suite

@app.put("/v1/superadmin/simulations/test-suites/{suite_id}")
async def update_test_suite(suite_id: str, request: Request):
    _verify_superadmin(request)
    body = await request.json()
    return behavior_tests.update_suite(suite_id, body)

@app.post("/v1/superadmin/simulations/test-suites/{suite_id}/run")
async def run_test_suite(suite_id: str, request: Request):
    _verify_superadmin(request)
    body = await request.json()
    return await behavior_tests.run_suite(suite_id, agent_ids=body.get("agent_ids"))

@app.get("/v1/superadmin/simulations/test-runs/{run_id}")
async def get_test_run_results(run_id: str, request: Request):
    _verify_superadmin(request)
    run = behavior_tests.get_run_results(run_id)
    if not run:
        raise HTTPException(404, "Run not found")
    return run

@app.get("/v1/superadmin/simulations/test-suites/{suite_id}/history")
async def get_test_suite_history(suite_id: str, request: Request):
    _verify_superadmin(request)
    return {"history": behavior_tests.get_suite_history(suite_id)}


# ── SuperAdmin: A/B Testing ──────────────────────────

@app.post("/v1/superadmin/simulations/ab-tests")
async def create_ab_experiment(request: Request):
    _verify_superadmin(request)
    body = await request.json()
    if not body.get("name") or not body.get("variant_a") or not body.get("variant_b"):
        raise HTTPException(400, "name, variant_a, and variant_b required")
    return ab_testing.create_experiment(
        body["name"], body["variant_a"], body["variant_b"],
        body.get("agent_ids", []), body.get("task_prompts", []), config=body.get("config"))

@app.get("/v1/superadmin/simulations/ab-tests")
async def list_ab_experiments(request: Request):
    _verify_superadmin(request)
    return {"experiments": ab_testing.list_experiments(status=request.query_params.get("status"))}

@app.get("/v1/superadmin/simulations/ab-tests/stats")
async def get_ab_stats(request: Request):
    _verify_superadmin(request)
    return ab_testing.get_stats()

@app.get("/v1/superadmin/simulations/ab-tests/{experiment_id}")
async def get_ab_experiment(experiment_id: str, request: Request):
    _verify_superadmin(request)
    exp = ab_testing.get_experiment(experiment_id)
    if not exp:
        raise HTTPException(404, "Experiment not found")
    return exp

@app.post("/v1/superadmin/simulations/ab-tests/{experiment_id}/run")
async def run_ab_experiment(experiment_id: str, request: Request):
    _verify_superadmin(request)
    return await ab_testing.run_experiment(experiment_id)

@app.post("/v1/superadmin/simulations/ab-tests/{experiment_id}/apply")
async def apply_ab_winner(experiment_id: str, request: Request):
    _verify_superadmin(request)
    return ab_testing.apply_winner(experiment_id)


# ── SuperAdmin: Chaos Injection ──────────────────────────

@app.post("/v1/superadmin/simulations/{sim_id}/chaos")
async def inject_chaos(sim_id: str, request: Request):
    _verify_superadmin(request)
    body = await request.json()
    if not body.get("event_type") or not body.get("target"):
        raise HTTPException(400, "event_type and target required")
    return chaos_injector.inject_failure(sim_id, body["event_type"], body["target"], config=body.get("config"))

@app.get("/v1/superadmin/simulations/{sim_id}/chaos")
async def get_chaos_events(sim_id: str, request: Request):
    _verify_superadmin(request)
    return {"events": chaos_injector.get_chaos_events(sim_id)}

@app.get("/v1/superadmin/simulations/chaos/{event_id}/recovery")
async def evaluate_chaos_recovery(event_id: str, request: Request):
    _verify_superadmin(request)
    return chaos_injector.evaluate_recovery(event_id)

@app.post("/v1/superadmin/simulations/chaos/scenario")
async def run_chaos_scenario(request: Request):
    _verify_superadmin(request)
    body = await request.json()
    if not body.get("name") or not body.get("events_sequence"):
        raise HTTPException(400, "name and events_sequence required")
    return await chaos_injector.run_chaos_scenario(
        body["name"], body.get("agent_ids", []), body["events_sequence"])

@app.get("/v1/superadmin/simulations/chaos/catalog")
async def get_chaos_catalog(request: Request):
    _verify_superadmin(request)
    return {"catalog": chaos_injector.get_chaos_catalog()}

@app.get("/v1/superadmin/simulations/chaos/stats")
async def get_chaos_stats(request: Request):
    _verify_superadmin(request)
    return chaos_injector.get_stats()


# ── Autonomy Loop ──────────────────────────────────────────────

@app.get("/api/v1/superadmin/autonomy/status")
async def autonomy_status():
    return autonomy_loop.get_status()

@app.get("/api/v1/superadmin/autonomy/agents")
async def autonomy_all_configs():
    return {"agents": autonomy_loop.get_all_configs()}

@app.get("/api/v1/superadmin/autonomy/agents/{agent_id}")
async def autonomy_agent_status(agent_id: str):
    return autonomy_loop.get_agent_status(agent_id)

@app.post("/api/v1/superadmin/autonomy/agents/{agent_id}/configure")
async def autonomy_configure(agent_id: str, request: Request):
    body = await request.json()
    return autonomy_loop.configure_agent(agent_id, body)

@app.post("/api/v1/superadmin/autonomy/agents/{agent_id}/start")
async def autonomy_start(agent_id: str):
    return await autonomy_loop.start_agent(agent_id)

@app.post("/api/v1/superadmin/autonomy/agents/{agent_id}/stop")
async def autonomy_stop(agent_id: str):
    return await autonomy_loop.stop_agent(agent_id)

@app.post("/api/v1/superadmin/autonomy/agents/{agent_id}/cycle")
async def autonomy_run_cycle(agent_id: str):
    return await autonomy_loop.run_single_cycle(agent_id)

@app.get("/api/v1/superadmin/autonomy/history")
async def autonomy_history(agent_id: str = None, limit: int = 50):
    return {"history": autonomy_loop.get_cycle_history(agent_id, limit)}


# ── SuperAdmin: Marketplace ────────────────────────────

@app.get("/v1/superadmin/marketplace/capabilities")
async def list_marketplace_capabilities(request: Request, category: str = None, enabled_only: bool = False):
    """List all marketplace capabilities with optional filters."""
    _verify_superadmin(request)
    caps = marketplace.list_capabilities(category=category, enabled_only=enabled_only)
    return {"capabilities": [c.to_dict() for c in caps]}

@app.get("/v1/superadmin/marketplace/stats")
async def get_marketplace_stats(request: Request):
    """Get marketplace summary statistics."""
    _verify_superadmin(request)
    return marketplace.get_marketplace_stats()

@app.get("/v1/superadmin/marketplace/search")
async def search_marketplace(request: Request, q: str = ""):
    """Search marketplace capabilities by name or description."""
    _verify_superadmin(request)
    if not q.strip():
        caps = marketplace.list_capabilities()
    else:
        caps = marketplace.search_capabilities(q)
    return {"capabilities": [c.to_dict() for c in caps], "query": q}

@app.get("/v1/superadmin/marketplace/capabilities/{capability_id}")
async def get_marketplace_capability(capability_id: str, request: Request):
    """Get a single marketplace capability."""
    _verify_superadmin(request)
    cap = marketplace.get_capability(capability_id)
    if not cap:
        raise HTTPException(404, f"Capability '{capability_id}' not found")
    return cap.to_dict()

@app.post("/v1/superadmin/marketplace/capabilities/{capability_id}/enable")
async def enable_marketplace_capability(capability_id: str, request: Request):
    """Enable a marketplace capability."""
    _verify_superadmin(request)
    result = marketplace.enable_capability(capability_id)
    if not result.get("success"):
        raise HTTPException(400, result.get("error", "Failed to enable capability"))
    await _push_typed_event("marketplace_capability_enabled", {"capability_id": capability_id}, "marketplace")
    return result

@app.post("/v1/superadmin/marketplace/capabilities/{capability_id}/disable")
async def disable_marketplace_capability(capability_id: str, request: Request):
    """Disable a marketplace capability."""
    _verify_superadmin(request)
    result = marketplace.disable_capability(capability_id)
    if not result.get("success"):
        raise HTTPException(400, result.get("error", "Failed to disable capability"))
    await _push_typed_event("marketplace_capability_disabled", {"capability_id": capability_id}, "marketplace")
    return result

@app.put("/v1/superadmin/marketplace/capabilities/{capability_id}/config")
async def update_marketplace_capability_config(capability_id: str, request: Request):
    """Update configuration for a marketplace capability."""
    _verify_superadmin(request)
    body = await request.json()
    config = body.get("config", {})
    if not isinstance(config, dict):
        raise HTTPException(400, "config must be a JSON object")
    result = marketplace.update_capability_config(capability_id, config)
    if not result.get("success"):
        raise HTTPException(400, result.get("error", "Failed to update config"))
    return result

@app.get("/v1/superadmin/marketplace/capabilities/{capability_id}/dependencies")
async def check_capability_dependencies(capability_id: str, request: Request):
    """Check dependency status for a capability."""
    _verify_superadmin(request)
    return marketplace.check_dependencies(capability_id)

@app.get("/v1/superadmin/marketplace/capabilities/{capability_id}/dependents")
async def get_capability_dependents(capability_id: str, request: Request):
    """Get capabilities that depend on this one."""
    _verify_superadmin(request)
    dependents = marketplace.get_dependents(capability_id)
    return {"dependents": [d.to_dict() for d in dependents]}


# ── SuperAdmin: Plugin System ─────────────────────────

@app.get("/v1/superadmin/plugins")
async def list_plugins(request: Request, enabled_only: bool = False):
    """List all installed plugins."""
    _verify_superadmin(request)
    plugins = plugin_manager.list_plugins(enabled_only=enabled_only)
    return {"plugins": [p for p in plugins]}

@app.get("/v1/superadmin/plugins/stats")
async def get_plugin_stats(request: Request):
    """Get plugin system statistics."""
    _verify_superadmin(request)
    return plugin_manager.get_plugin_stats()

@app.get("/v1/superadmin/plugins/{plugin_id}")
async def get_plugin(plugin_id: str, request: Request):
    """Get a single plugin."""
    _verify_superadmin(request)
    plugin = plugin_manager.get_plugin(plugin_id)
    if not plugin:
        raise HTTPException(404, f"Plugin '{plugin_id}' not found")
    return plugin

@app.post("/v1/superadmin/plugins")
async def register_plugin(request: Request):
    """Register a new plugin from its manifest."""
    _verify_superadmin(request)
    body = await request.json()
    result = plugin_manager.register_plugin(body)
    if "error" in result:
        raise HTTPException(400, result["error"])
    await _push_typed_event("plugin_registered", {"plugin_id": result.get("id", "")}, "plugins")
    return result

@app.delete("/v1/superadmin/plugins/{plugin_id}")
async def unregister_plugin(plugin_id: str, request: Request):
    """Unregister/remove a plugin."""
    _verify_superadmin(request)
    result = plugin_manager.unregister_plugin(plugin_id)
    if "error" in result:
        raise HTTPException(404, result["error"])
    await _push_typed_event("plugin_unregistered", {"plugin_id": plugin_id}, "plugins")
    return result

@app.post("/v1/superadmin/plugins/{plugin_id}/enable")
async def enable_plugin(plugin_id: str, request: Request):
    """Enable a plugin."""
    _verify_superadmin(request)
    result = plugin_manager.enable_plugin(plugin_id)
    if "error" in result:
        raise HTTPException(400, result["error"])
    return result

@app.post("/v1/superadmin/plugins/{plugin_id}/disable")
async def disable_plugin(plugin_id: str, request: Request):
    """Disable a plugin."""
    _verify_superadmin(request)
    result = plugin_manager.disable_plugin(plugin_id)
    if "error" in result:
        raise HTTPException(400, result["error"])
    return result


# ── SuperAdmin: AI Copilot ────────────────────────────

@app.get("/v1/superadmin/copilot/sessions")
async def copilot_list_sessions(request: Request):
    _verify_superadmin(request)
    return {"sessions": copilot.list_sessions()}

@app.post("/v1/superadmin/copilot/sessions")
async def copilot_create_session(request: Request):
    _verify_superadmin(request)
    body = await request.json()
    return copilot.create_session(title=body.get("title"))

@app.get("/v1/superadmin/copilot/sessions/{session_id}")
async def copilot_get_session(session_id: str, request: Request):
    _verify_superadmin(request)
    result = copilot.get_session(session_id)
    if not result:
        raise HTTPException(404, "Session not found")
    return result

@app.delete("/v1/superadmin/copilot/sessions/{session_id}")
async def copilot_delete_session(session_id: str, request: Request):
    _verify_superadmin(request)
    return copilot.delete_session(session_id)

@app.post("/v1/superadmin/copilot/chat")
async def copilot_chat(request: Request):
    _verify_superadmin(request)
    body = await request.json()
    session_id = body.get("session_id", "")
    message = body.get("message", "")
    if not message:
        raise HTTPException(400, "message required")
    return copilot.chat(session_id, message, context=body.get("context"))

@app.post("/v1/superadmin/copilot/generate-query")
async def copilot_generate_query(request: Request):
    _verify_superadmin(request)
    body = await request.json()
    return copilot.generate_query(body.get("description", ""))

@app.get("/v1/superadmin/copilot/explain-agent/{agent_id}")
async def copilot_explain_agent(agent_id: str, request: Request):
    _verify_superadmin(request)
    return copilot.explain_agent(agent_id)

@app.get("/v1/superadmin/copilot/suggest-optimizations")
async def copilot_suggest_optimizations(request: Request):
    _verify_superadmin(request)
    return copilot.suggest_optimizations()

@app.get("/v1/superadmin/copilot/stats")
async def copilot_stats(request: Request):
    _verify_superadmin(request)
    return copilot.get_stats()


# ── SuperAdmin: Template Marketplace ──────────────────

@app.get("/v1/superadmin/template-market/templates")
async def template_market_list(request: Request, category: str = None, search: str = None, sort_by: str = "downloads"):
    _verify_superadmin(request)
    return {"templates": template_market.list_templates(category=category, sort_by=sort_by, search=search)}

@app.get("/v1/superadmin/template-market/categories")
async def template_market_categories(request: Request):
    _verify_superadmin(request)
    return {"categories": template_market.get_categories()}

@app.get("/v1/superadmin/template-market/stats")
async def template_market_stats(request: Request):
    _verify_superadmin(request)
    return template_market.get_stats()

@app.get("/v1/superadmin/template-market/featured")
async def template_market_featured(request: Request):
    _verify_superadmin(request)
    return {"templates": template_market.get_featured()}

@app.get("/v1/superadmin/template-market/templates/{template_id}")
async def template_market_get(template_id: str, request: Request):
    _verify_superadmin(request)
    result = template_market.get_template(template_id)
    if not result:
        raise HTTPException(404, "Template not found")
    return result

@app.post("/v1/superadmin/template-market/templates/{template_id}/install")
async def template_market_install(template_id: str, request: Request):
    _verify_superadmin(request)
    result = template_market.install_template(template_id)
    if "error" in result:
        raise HTTPException(400, result["error"])
    return result

@app.post("/v1/superadmin/template-market/templates/{template_id}/rate")
async def template_market_rate(template_id: str, request: Request):
    _verify_superadmin(request)
    body = await request.json()
    return template_market.rate_template(template_id, body.get("rating", 5))

@app.post("/v1/superadmin/template-market/templates")
async def template_market_publish(request: Request):
    _verify_superadmin(request)
    body = await request.json()
    return template_market.publish_template(body)


# ── SuperAdmin: GraphQL Gateway ───────────────────────

@app.post("/v1/superadmin/graphql/execute")
async def graphql_execute(request: Request):
    _verify_superadmin(request)
    body = await request.json()
    return graphql_gw.execute_query(body.get("query", ""), variables=body.get("variables"))

@app.get("/v1/superadmin/graphql/schema")
async def graphql_schema(request: Request):
    _verify_superadmin(request)
    return graphql_gw.get_schema()

@app.post("/v1/superadmin/graphql/generate")
async def graphql_generate(request: Request):
    _verify_superadmin(request)
    return graphql_gw.generate_schema()

@app.get("/v1/superadmin/graphql/log")
async def graphql_log(request: Request, limit: int = 50):
    _verify_superadmin(request)
    return {"queries": graphql_gw.get_query_log(limit=limit)}

@app.get("/v1/superadmin/graphql/stats")
async def graphql_stats(request: Request):
    _verify_superadmin(request)
    return graphql_gw.get_stats()

@app.get("/v1/superadmin/graphql/introspect")
async def graphql_introspect(request: Request):
    _verify_superadmin(request)
    return graphql_gw.introspect()


# ── SuperAdmin: Teams Integration ─────────────────────

@app.post("/v1/superadmin/integrations/teams/configure")
async def teams_configure(request: Request):
    _verify_superadmin(request)
    body = await request.json()
    return teams_integration.configure(body.get("webhook_url", ""), bot_token=body.get("bot_token"), channel_mappings=body.get("channel_mappings"))

@app.get("/v1/superadmin/integrations/teams/config")
async def teams_get_config(request: Request):
    _verify_superadmin(request)
    return teams_integration.get_config()

@app.post("/v1/superadmin/integrations/teams/test")
async def teams_test(request: Request):
    _verify_superadmin(request)
    return teams_integration.test_connection()

@app.get("/v1/superadmin/integrations/teams/messages")
async def teams_messages(request: Request, limit: int = 50):
    _verify_superadmin(request)
    return {"messages": teams_integration.list_messages(limit=limit)}

@app.get("/v1/superadmin/integrations/teams/stats")
async def teams_stats(request: Request):
    _verify_superadmin(request)
    return teams_integration.get_stats()


# ── SuperAdmin: Discord Integration ───────────────────

@app.post("/v1/superadmin/integrations/discord/configure")
async def discord_configure(request: Request):
    _verify_superadmin(request)
    body = await request.json()
    return discord_integration.configure(bot_token=body.get("bot_token"), webhook_url=body.get("webhook_url"), guild_id=body.get("guild_id"))

@app.get("/v1/superadmin/integrations/discord/config")
async def discord_get_config(request: Request):
    _verify_superadmin(request)
    return discord_integration.get_config()

@app.post("/v1/superadmin/integrations/discord/test")
async def discord_test(request: Request):
    _verify_superadmin(request)
    return discord_integration.test_connection()

@app.get("/v1/superadmin/integrations/discord/messages")
async def discord_messages(request: Request, limit: int = 50):
    _verify_superadmin(request)
    return {"messages": discord_integration.list_messages(limit=limit)}

@app.get("/v1/superadmin/integrations/discord/stats")
async def discord_stats(request: Request):
    _verify_superadmin(request)
    return discord_integration.get_stats()


# ── SuperAdmin: Zapier / n8n Connector ────────────────

@app.post("/v1/superadmin/integrations/zapier/endpoints")
async def zapier_create_endpoint(request: Request):
    _verify_superadmin(request)
    body = await request.json()
    return zapier_connector.create_endpoint(body.get("name", ""), body.get("url", ""), body.get("event_types", []), secret=body.get("secret"), headers=body.get("headers"))

@app.get("/v1/superadmin/integrations/zapier/endpoints")
async def zapier_list_endpoints(request: Request):
    _verify_superadmin(request)
    return {"endpoints": zapier_connector.list_endpoints()}

@app.get("/v1/superadmin/integrations/zapier/endpoints/{endpoint_id}")
async def zapier_get_endpoint(endpoint_id: str, request: Request):
    _verify_superadmin(request)
    result = zapier_connector.get_endpoint(endpoint_id)
    if not result:
        raise HTTPException(404, "Endpoint not found")
    return result

@app.delete("/v1/superadmin/integrations/zapier/endpoints/{endpoint_id}")
async def zapier_delete_endpoint(endpoint_id: str, request: Request):
    _verify_superadmin(request)
    return zapier_connector.delete_endpoint(endpoint_id)

@app.get("/v1/superadmin/integrations/zapier/deliveries")
async def zapier_deliveries(request: Request, endpoint_id: str = None, limit: int = 50):
    _verify_superadmin(request)
    return {"deliveries": zapier_connector.get_deliveries(endpoint_id=endpoint_id, limit=limit)}

@app.post("/v1/superadmin/integrations/zapier/deliveries/{delivery_id}/retry")
async def zapier_retry(delivery_id: str, request: Request):
    _verify_superadmin(request)
    return zapier_connector.retry_delivery(delivery_id)

@app.get("/v1/superadmin/integrations/zapier/events")
async def zapier_events(request: Request):
    _verify_superadmin(request)
    return {"events": zapier_connector.get_supported_events()}

@app.get("/v1/superadmin/integrations/zapier/stats")
async def zapier_stats(request: Request):
    _verify_superadmin(request)
    return zapier_connector.get_stats()


# ── SuperAdmin: Voice Interface ───────────────────────

@app.post("/v1/superadmin/voice/sessions")
async def voice_create_session(request: Request):
    _verify_superadmin(request)
    body = await request.json()
    return voice_interface.create_session(config=body.get("config"))

@app.post("/v1/superadmin/voice/process")
async def voice_process(request: Request):
    _verify_superadmin(request)
    body = await request.json()
    return voice_interface.process_command(body.get("session_id", ""), body.get("transcript", ""))

@app.get("/v1/superadmin/voice/commands")
async def voice_commands(request: Request):
    _verify_superadmin(request)
    return {"commands": voice_interface.get_supported_commands()}

@app.get("/v1/superadmin/voice/history")
async def voice_history(request: Request, session_id: str = None, limit: int = 50):
    _verify_superadmin(request)
    return {"history": voice_interface.get_command_history(session_id=session_id, limit=limit)}

@app.get("/v1/superadmin/voice/config")
async def voice_get_config(request: Request):
    _verify_superadmin(request)
    return voice_interface.get_voice_config()

@app.put("/v1/superadmin/voice/config")
async def voice_update_config(request: Request):
    _verify_superadmin(request)
    body = await request.json()
    return voice_interface.configure_voice(body)

@app.get("/v1/superadmin/voice/stats")
async def voice_stats(request: Request):
    _verify_superadmin(request)
    return voice_interface.get_stats()


# ── SuperAdmin: Zero-Trust ────────────────────────────

@app.get("/v1/superadmin/zero-trust/policies")
async def zt_list_policies(request: Request):
    _verify_superadmin(request)
    return {"policies": zero_trust.list_policies()}

@app.get("/v1/superadmin/zero-trust/policies/{policy_id}")
async def zt_get_policy(policy_id: str, request: Request):
    _verify_superadmin(request)
    result = zero_trust.get_policy(policy_id)
    if not result:
        raise HTTPException(404, "Policy not found")
    return result

@app.post("/v1/superadmin/zero-trust/policies")
async def zt_create_policy(request: Request):
    _verify_superadmin(request)
    body = await request.json()
    return zero_trust.create_policy(body.get("name", ""), body.get("policy_type", "deny"), body.get("source_pattern", "*"), body.get("destination_pattern", "*"), conditions=body.get("conditions"), priority=body.get("priority", 100))

@app.put("/v1/superadmin/zero-trust/policies/{policy_id}")
async def zt_update_policy(policy_id: str, request: Request):
    _verify_superadmin(request)
    body = await request.json()
    return zero_trust.update_policy(policy_id, body)

@app.delete("/v1/superadmin/zero-trust/policies/{policy_id}")
async def zt_delete_policy(policy_id: str, request: Request):
    _verify_superadmin(request)
    return zero_trust.delete_policy(policy_id)

@app.get("/v1/superadmin/zero-trust/certificates")
async def zt_list_certs(request: Request):
    _verify_superadmin(request)
    return {"certificates": zero_trust.list_certificates()}

@app.post("/v1/superadmin/zero-trust/certificates")
async def zt_issue_cert(request: Request):
    _verify_superadmin(request)
    body = await request.json()
    return zero_trust.issue_certificate(body.get("subject", ""))

@app.post("/v1/superadmin/zero-trust/certificates/{cert_id}/revoke")
async def zt_revoke_cert(cert_id: str, request: Request):
    _verify_superadmin(request)
    return zero_trust.revoke_certificate(cert_id)

@app.get("/v1/superadmin/zero-trust/audit")
async def zt_audit(request: Request, limit: int = 100):
    _verify_superadmin(request)
    return {"audit_log": zero_trust.get_audit_log(limit=limit)}

@app.get("/v1/superadmin/zero-trust/stats")
async def zt_stats(request: Request):
    _verify_superadmin(request)
    return zero_trust.get_stats()


# ── SuperAdmin: Secrets Vault ─────────────────────────

@app.get("/v1/superadmin/vault/secrets")
async def vault_list(request: Request, prefix: str = None):
    _verify_superadmin(request)
    return {"secrets": secrets_vault_v2.list_secrets(prefix=prefix)}

@app.get("/v1/superadmin/vault/secrets/{path:path}")
async def vault_get(path: str, request: Request):
    _verify_superadmin(request)
    result = secrets_vault_v2.get_secret(path)
    if "error" in result:
        raise HTTPException(404, result["error"])
    return result

@app.post("/v1/superadmin/vault/secrets")
async def vault_put(request: Request):
    _verify_superadmin(request)
    body = await request.json()
    return secrets_vault_v2.put_secret(body.get("path", ""), body.get("value", ""), metadata=body.get("metadata"))

@app.delete("/v1/superadmin/vault/secrets/{path:path}")
async def vault_delete(path: str, request: Request):
    _verify_superadmin(request)
    return secrets_vault_v2.delete_secret(path)

@app.post("/v1/superadmin/vault/secrets/{path:path}/rotate")
async def vault_rotate(path: str, request: Request):
    _verify_superadmin(request)
    return secrets_vault_v2.rotate_secret(path)

@app.get("/v1/superadmin/vault/rotation-schedule")
async def vault_rotation_schedule(request: Request):
    _verify_superadmin(request)
    return {"schedule": secrets_vault_v2.get_rotation_schedule()}

@app.get("/v1/superadmin/vault/status")
async def vault_status(request: Request):
    _verify_superadmin(request)
    return secrets_vault_v2.get_vault_status()

@app.get("/v1/superadmin/vault/stats")
async def vault_stats(request: Request):
    _verify_superadmin(request)
    return secrets_vault_v2.get_stats()


# ── SuperAdmin: Data Pipeline Builder ─────────────────

@app.post("/v1/superadmin/data-pipelines")
async def pipeline_create(request: Request):
    _verify_superadmin(request)
    body = await request.json()
    return pipeline_builder.create_pipeline(body.get("name", ""), description=body.get("description"), stages=body.get("stages"), schedule=body.get("schedule"))

@app.get("/v1/superadmin/data-pipelines")
async def pipeline_list(request: Request, status: str = None):
    _verify_superadmin(request)
    return {"pipelines": pipeline_builder.list_pipelines(status=status)}

@app.get("/v1/superadmin/data-pipelines/stage-types")
async def pipeline_stage_types(request: Request):
    _verify_superadmin(request)
    return {"stage_types": pipeline_builder.get_stage_types()}

@app.get("/v1/superadmin/data-pipelines/stats")
async def pipeline_stats(request: Request):
    _verify_superadmin(request)
    return pipeline_builder.get_stats()

@app.get("/v1/superadmin/data-pipelines/runs")
async def pipeline_list_runs(request: Request, pipeline_id: str = None):
    _verify_superadmin(request)
    return {"runs": pipeline_builder.list_runs(pipeline_id=pipeline_id)}

@app.get("/v1/superadmin/data-pipelines/{pipeline_id}")
async def pipeline_get(pipeline_id: str, request: Request):
    _verify_superadmin(request)
    result = pipeline_builder.get_pipeline(pipeline_id)
    if not result:
        raise HTTPException(404, "Pipeline not found")
    return result

@app.put("/v1/superadmin/data-pipelines/{pipeline_id}")
async def pipeline_update(pipeline_id: str, request: Request):
    _verify_superadmin(request)
    body = await request.json()
    return pipeline_builder.update_pipeline(pipeline_id, body)

@app.delete("/v1/superadmin/data-pipelines/{pipeline_id}")
async def pipeline_delete(pipeline_id: str, request: Request):
    _verify_superadmin(request)
    return pipeline_builder.delete_pipeline(pipeline_id)

@app.post("/v1/superadmin/data-pipelines/{pipeline_id}/execute")
async def pipeline_execute(pipeline_id: str, request: Request):
    _verify_superadmin(request)
    return pipeline_builder.execute_pipeline(pipeline_id)


# ── SuperAdmin: Custom Dashboards ─────────────────────

@app.post("/v1/superadmin/custom-dashboards")
async def custom_dashboard_create(request: Request):
    _verify_superadmin(request)
    body = await request.json()
    return custom_dashboards.create_dashboard(body.get("name", ""), description=body.get("description"), layout=body.get("layout"))

@app.get("/v1/superadmin/custom-dashboards")
async def custom_dashboard_list(request: Request):
    _verify_superadmin(request)
    return {"dashboards": custom_dashboards.list_dashboards()}

@app.get("/v1/superadmin/custom-dashboards/widget-types")
async def custom_dashboard_widget_types(request: Request):
    _verify_superadmin(request)
    return {"widget_types": custom_dashboards.get_widget_types()}

@app.get("/v1/superadmin/custom-dashboards/stats")
async def custom_dashboard_stats(request: Request):
    _verify_superadmin(request)
    return custom_dashboards.get_stats()

@app.get("/v1/superadmin/custom-dashboards/{dashboard_id}")
async def custom_dashboard_get(dashboard_id: str, request: Request):
    _verify_superadmin(request)
    result = custom_dashboards.get_dashboard(dashboard_id)
    if not result:
        raise HTTPException(404, "Dashboard not found")
    return result

@app.put("/v1/superadmin/custom-dashboards/{dashboard_id}")
async def custom_dashboard_update(dashboard_id: str, request: Request):
    _verify_superadmin(request)
    body = await request.json()
    return custom_dashboards.update_dashboard(dashboard_id, body)

@app.delete("/v1/superadmin/custom-dashboards/{dashboard_id}")
async def custom_dashboard_delete(dashboard_id: str, request: Request):
    _verify_superadmin(request)
    return custom_dashboards.delete_dashboard(dashboard_id)

@app.post("/v1/superadmin/custom-dashboards/{dashboard_id}/duplicate")
async def custom_dashboard_duplicate(dashboard_id: str, request: Request):
    _verify_superadmin(request)
    body = await request.json()
    return custom_dashboards.duplicate_dashboard(dashboard_id, body.get("new_name", "Copy"))

@app.post("/v1/superadmin/custom-dashboards/{dashboard_id}/widgets")
async def custom_dashboard_add_widget(dashboard_id: str, request: Request):
    _verify_superadmin(request)
    body = await request.json()
    return custom_dashboards.add_widget(dashboard_id, body.get("widget_type", ""), body.get("title", ""), body.get("data_source", ""), config=body.get("config"), position=body.get("position"))

@app.delete("/v1/superadmin/custom-dashboards/widgets/{widget_id}")
async def custom_dashboard_remove_widget(widget_id: str, request: Request):
    _verify_superadmin(request)
    return custom_dashboards.remove_widget(widget_id)


# ── SuperAdmin: Edge Deployment ───────────────────────

@app.post("/v1/superadmin/edge/nodes")
async def edge_register(request: Request):
    _verify_superadmin(request)
    body = await request.json()
    return edge_manager.register_node(body.get("name", ""), body.get("location", ""), body.get("region", ""), config=body.get("config"), max_storage_mb=body.get("max_storage_mb", 1024))

@app.get("/v1/superadmin/edge/nodes")
async def edge_list(request: Request, region: str = None):
    _verify_superadmin(request)
    return {"nodes": edge_manager.list_nodes(region=region)}

@app.get("/v1/superadmin/edge/stats")
async def edge_stats(request: Request):
    _verify_superadmin(request)
    return edge_manager.get_stats()

@app.get("/v1/superadmin/edge/sync-log")
async def edge_sync_log(request: Request, node_id: str = None):
    _verify_superadmin(request)
    return {"sync_log": edge_manager.get_sync_log(node_id=node_id)}

@app.get("/v1/superadmin/edge/nodes/{node_id}")
async def edge_get(node_id: str, request: Request):
    _verify_superadmin(request)
    result = edge_manager.get_node(node_id)
    if not result:
        raise HTTPException(404, "Edge node not found")
    return result

@app.delete("/v1/superadmin/edge/nodes/{node_id}")
async def edge_remove(node_id: str, request: Request):
    _verify_superadmin(request)
    return edge_manager.remove_node(node_id)

@app.post("/v1/superadmin/edge/nodes/{node_id}/sync")
async def edge_sync(node_id: str, request: Request):
    _verify_superadmin(request)
    body = await request.json()
    return edge_manager.sync_data(node_id, direction=body.get("direction", "push"))


# ── SuperAdmin: Kubernetes Operator ───────────────────

@app.post("/v1/superadmin/kubernetes/clusters")
async def k8s_register(request: Request):
    _verify_superadmin(request)
    body = await request.json()
    return k8s_operator.register_cluster(body.get("name", ""), namespace=body.get("namespace", "cortexdb"), config=body.get("config"))

@app.get("/v1/superadmin/kubernetes/clusters")
async def k8s_list(request: Request):
    _verify_superadmin(request)
    return {"clusters": k8s_operator.list_clusters()}

@app.get("/v1/superadmin/kubernetes/stats")
async def k8s_stats(request: Request):
    _verify_superadmin(request)
    return k8s_operator.get_stats()

@app.get("/v1/superadmin/kubernetes/operations")
async def k8s_operations(request: Request, cluster_id: str = None):
    _verify_superadmin(request)
    return {"operations": k8s_operator.get_operations(cluster_id=cluster_id)}

@app.get("/v1/superadmin/kubernetes/clusters/{cluster_id}")
async def k8s_get(cluster_id: str, request: Request):
    _verify_superadmin(request)
    result = k8s_operator.get_cluster(cluster_id)
    if not result:
        raise HTTPException(404, "Cluster not found")
    return result

@app.post("/v1/superadmin/kubernetes/clusters/{cluster_id}/scale")
async def k8s_scale(cluster_id: str, request: Request):
    _verify_superadmin(request)
    body = await request.json()
    return k8s_operator.scale(cluster_id, body.get("component", ""), body.get("replicas", 1))

@app.post("/v1/superadmin/kubernetes/clusters/{cluster_id}/upgrade")
async def k8s_upgrade(cluster_id: str, request: Request):
    _verify_superadmin(request)
    body = await request.json()
    return k8s_operator.rolling_upgrade(cluster_id, body.get("image", ""))

@app.post("/v1/superadmin/kubernetes/manifests")
async def k8s_manifests(request: Request):
    _verify_superadmin(request)
    body = await request.json()
    return k8s_operator.generate_manifests(config=body)


# ── SuperAdmin: White-Label & Theming ─────────────────

@app.get("/v1/superadmin/theming/themes")
async def theme_list(request: Request):
    _verify_superadmin(request)
    return {"themes": white_label.list_themes()}

@app.get("/v1/superadmin/theming/active")
async def theme_active(request: Request):
    _verify_superadmin(request)
    return white_label.get_active_theme()

@app.get("/v1/superadmin/theming/stats")
async def theme_stats(request: Request):
    _verify_superadmin(request)
    return white_label.get_stats()

@app.get("/v1/superadmin/theming/themes/{theme_id}")
async def theme_get(theme_id: str, request: Request):
    _verify_superadmin(request)
    result = white_label.get_theme(theme_id)
    if not result:
        raise HTTPException(404, "Theme not found")
    return result

@app.post("/v1/superadmin/theming/themes")
async def theme_create(request: Request):
    _verify_superadmin(request)
    body = await request.json()
    return white_label.create_theme(body.get("name", ""), body.get("colors", {}), typography=body.get("typography"), logo_url=body.get("logo_url"))

@app.post("/v1/superadmin/theming/themes/{theme_id}/activate")
async def theme_activate(theme_id: str, request: Request):
    _verify_superadmin(request)
    return white_label.activate_theme(theme_id)

@app.delete("/v1/superadmin/theming/themes/{theme_id}")
async def theme_delete(theme_id: str, request: Request):
    _verify_superadmin(request)
    return white_label.delete_theme(theme_id)

@app.get("/v1/superadmin/theming/branding")
async def branding_get(request: Request):
    _verify_superadmin(request)
    return white_label.get_branding()

@app.put("/v1/superadmin/theming/branding")
async def branding_update(request: Request):
    _verify_superadmin(request)
    body = await request.json()
    return white_label.update_branding(body)


# ── SuperAdmin: Multi-Region ──────────────────────────

@app.get("/v1/superadmin/regions")
async def region_list(request: Request):
    _verify_superadmin(request)
    return {"regions": multi_region.list_regions()}

@app.get("/v1/superadmin/regions/health")
async def region_health(request: Request):
    _verify_superadmin(request)
    return multi_region.get_health()

@app.get("/v1/superadmin/regions/stats")
async def region_stats(request: Request):
    _verify_superadmin(request)
    return multi_region.get_stats()

@app.get("/v1/superadmin/regions/streams")
async def region_list_streams(request: Request):
    _verify_superadmin(request)
    return {"streams": multi_region.list_streams()}

@app.get("/v1/superadmin/regions/conflicts")
async def region_list_conflicts(request: Request):
    _verify_superadmin(request)
    return {"conflicts": multi_region.list_conflicts()}

@app.post("/v1/superadmin/regions")
async def region_add(request: Request):
    _verify_superadmin(request)
    body = await request.json()
    return multi_region.add_region(body.get("name", ""), body.get("display_name", ""), body.get("endpoint", ""), config=body.get("config"))

@app.get("/v1/superadmin/regions/{region_id}")
async def region_get(region_id: str, request: Request):
    _verify_superadmin(request)
    result = multi_region.get_region(region_id)
    if not result:
        raise HTTPException(404, "Region not found")
    return result

@app.delete("/v1/superadmin/regions/{region_id}")
async def region_remove(region_id: str, request: Request):
    _verify_superadmin(request)
    return multi_region.remove_region(region_id)

@app.post("/v1/superadmin/regions/{region_id}/set-primary")
async def region_set_primary(region_id: str, request: Request):
    _verify_superadmin(request)
    return multi_region.set_primary(region_id)

@app.post("/v1/superadmin/regions/streams")
async def region_create_stream(request: Request):
    _verify_superadmin(request)
    body = await request.json()
    return multi_region.create_replication_stream(body.get("source", ""), body.get("target", ""), tables=body.get("tables"), config=body.get("config"))

@app.post("/v1/superadmin/regions/conflicts/{conflict_id}/resolve")
async def region_resolve_conflict(conflict_id: str, request: Request):
    _verify_superadmin(request)
    body = await request.json()
    return multi_region.resolve_conflict(conflict_id, body.get("resolution", "source_wins"))

@app.post("/v1/superadmin/regions/failover")
async def region_failover(request: Request):
    _verify_superadmin(request)
    body = await request.json()
    return multi_region.trigger_failover(body.get("from_region", ""), body.get("to_region", ""), reason=body.get("reason"))


# ── SuperAdmin: Sentinel (Security Testing) ───────────

@app.get("/v1/superadmin/sentinel/stats")
async def sentinel_stats(request: Request):
    _verify_superadmin(request)
    return sentinel.get_stats()

@app.post("/v1/superadmin/sentinel/quick-scan")
async def sentinel_quick_scan(request: Request):
    _verify_superadmin(request)
    return await sentinel.run_quick_scan()

@app.get("/v1/superadmin/sentinel/knowledge")
async def sentinel_knowledge(request: Request, category: str = None):
    _verify_superadmin(request)
    return {"vectors": sentinel.list_attack_vectors(category=category)}

@app.get("/v1/superadmin/sentinel/knowledge/{attack_id}")
async def sentinel_knowledge_detail(attack_id: str, request: Request):
    _verify_superadmin(request)
    result = sentinel.get_attack_vector(attack_id)
    if not result:
        raise HTTPException(404, "Attack vector not found")
    return result

@app.post("/v1/superadmin/sentinel/knowledge")
async def sentinel_add_vector(request: Request):
    _verify_superadmin(request)
    body = await request.json()
    return sentinel.add_attack_vector(body)

@app.get("/v1/superadmin/sentinel/campaigns")
async def sentinel_campaigns(request: Request, status: str = None):
    _verify_superadmin(request)
    return {"campaigns": sentinel.list_campaigns(status=status)}

@app.post("/v1/superadmin/sentinel/campaigns")
async def sentinel_create_campaign(request: Request):
    _verify_superadmin(request)
    body = await request.json()
    return sentinel.create_campaign(
        name=body.get("name", ""),
        description=body.get("description", ""),
        categories=body.get("categories", []),
        aggression=body.get("aggression", 3),
        concurrency=body.get("concurrency", 5),
    )

@app.get("/v1/superadmin/sentinel/campaigns/{campaign_id}")
async def sentinel_get_campaign(campaign_id: str, request: Request):
    _verify_superadmin(request)
    result = sentinel.get_campaign(campaign_id)
    if not result:
        raise HTTPException(404, "Campaign not found")
    return result

@app.put("/v1/superadmin/sentinel/campaigns/{campaign_id}")
async def sentinel_update_campaign(campaign_id: str, request: Request):
    _verify_superadmin(request)
    body = await request.json()
    return sentinel.update_campaign(campaign_id, body)

@app.delete("/v1/superadmin/sentinel/campaigns/{campaign_id}")
async def sentinel_delete_campaign(campaign_id: str, request: Request):
    _verify_superadmin(request)
    return sentinel.delete_campaign(campaign_id)

@app.post("/v1/superadmin/sentinel/campaigns/{campaign_id}/execute")
async def sentinel_execute_campaign(campaign_id: str, request: Request):
    _verify_superadmin(request)
    return await sentinel.execute_campaign(campaign_id)

@app.get("/v1/superadmin/sentinel/runs")
async def sentinel_runs(request: Request, campaign_id: str = None):
    _verify_superadmin(request)
    return {"runs": sentinel.list_runs(campaign_id=campaign_id)}

@app.get("/v1/superadmin/sentinel/runs/{run_id}")
async def sentinel_get_run(run_id: str, request: Request):
    _verify_superadmin(request)
    result = sentinel.get_run(run_id)
    if not result:
        raise HTTPException(404, "Run not found")
    return result

@app.post("/v1/superadmin/sentinel/runs/{run_id}/abort")
async def sentinel_abort_run(run_id: str, request: Request):
    _verify_superadmin(request)
    return sentinel.abort_run(run_id)

@app.get("/v1/superadmin/sentinel/findings")
async def sentinel_findings(request: Request, category: str = None, severity: str = None, status: str = None, vulnerable_only: bool = False):
    _verify_superadmin(request)
    return {"findings": sentinel.list_findings(category=category, severity=severity, status=status, vulnerable_only=vulnerable_only)}

@app.put("/v1/superadmin/sentinel/findings/{finding_id}")
async def sentinel_update_finding(finding_id: str, request: Request):
    _verify_superadmin(request)
    body = await request.json()
    return sentinel.update_finding(finding_id, body)

@app.get("/v1/superadmin/sentinel/posture")
async def sentinel_posture(request: Request):
    _verify_superadmin(request)
    return sentinel.get_posture()

@app.get("/v1/superadmin/sentinel/posture/history")
async def sentinel_posture_history(request: Request):
    _verify_superadmin(request)
    return {"history": sentinel.get_posture_history()}

@app.get("/v1/superadmin/sentinel/posture/risks")
async def sentinel_risks(request: Request):
    _verify_superadmin(request)
    return {"risks": sentinel.get_risks()}

@app.get("/v1/superadmin/sentinel/remediation")
async def sentinel_remediation(request: Request, status: str = None):
    _verify_superadmin(request)
    return {"plans": sentinel.list_remediation_plans(status=status)}

@app.post("/v1/superadmin/sentinel/remediation/{finding_id}/generate")
async def sentinel_generate_remediation(finding_id: str, request: Request):
    _verify_superadmin(request)
    return await sentinel.generate_remediation(finding_id)

@app.put("/v1/superadmin/sentinel/remediation/{plan_id}")
async def sentinel_update_remediation(plan_id: str, request: Request):
    _verify_superadmin(request)
    body = await request.json()
    return sentinel.update_remediation_plan(plan_id, body)

@app.get("/v1/superadmin/sentinel/threat-intel")
async def sentinel_threat_intel(request: Request):
    _verify_superadmin(request)
    return {"intel": sentinel.list_threat_intel()}

@app.post("/v1/superadmin/sentinel/threat-intel")
async def sentinel_add_threat_intel(request: Request):
    _verify_superadmin(request)
    body = await request.json()
    return sentinel.add_threat_intel(body)


# ── WebSocket Real-Time Push ───────────────────────────

class ConnectionManager:
    """Manages WebSocket connections for real-time event push."""

    def __init__(self):
        self.active: list = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active.append(ws)

    def disconnect(self, ws: WebSocket):
        self.active.remove(ws)

    async def broadcast(self, event: dict):
        import json as _json
        msg = _json.dumps(event)
        dead = []
        for ws in self.active:
            try:
                await ws.send_text(msg)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.active.remove(ws)

ws_manager = ConnectionManager()

@app.websocket("/ws/events")
async def websocket_events(ws: WebSocket):
    """Real-time event stream for dashboard. Pushes task updates, agent state, bus messages."""
    # Verify auth from query params (WebSocket can't use headers easily)
    # Accept either admin token or superadmin session token
    token = ws.query_params.get("token", "")
    admin_token = os.environ.get("CORTEX_ADMIN_TOKEN", "")
    is_admin = admin_token and secrets.compare_digest(token, admin_token)
    is_superadmin = superadmin_auth.validate_session(token)
    if not is_admin and not is_superadmin:
        await ws.close(code=4001, reason="Unauthorized")
        return
    await ws_manager.connect(ws)
    try:
        while True:
            # Keep alive — also accept commands from client
            data = await ws.receive_text()
            if data == "ping":
                await ws.send_text('{"type":"pong"}')
    except WebSocketDisconnect:
        ws_manager.disconnect(ws)

# Helper to broadcast events from anywhere in the server
async def _push_event(event_type: str, data: dict):
    event = {"type": event_type, "data": data, "timestamp": time.time()}
    # Store for live feed replay
    if persistence_store:
        events = persistence_store.kv_get("live_feed_events", [])
        events.append(event)
        if len(events) > 500:
            events = events[-500:]
        persistence_store.kv_set("live_feed_events", events)
    if ws_manager.active:
        await ws_manager.broadcast(event)

async def _push_typed_event(event_type: str, data: dict, category: str = "general"):
    """Push event with category tracking."""
    await _push_event(event_type, {**data, "_category": category})
    # Track event counts
    if persistence_store:
        counts = persistence_store.kv_get("event_counts", {})
        counts[event_type] = counts.get(event_type, 0) + 1
        persistence_store.kv_set("event_counts", counts)

@app.get("/api/v1/superadmin/events/counts")
async def event_counts():
    counts = persistence_store.kv_get("event_counts", {})
    return {"counts": counts, "total": sum(counts.values())}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5400)

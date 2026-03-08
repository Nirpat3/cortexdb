"""
Agent Team Manager — Manages the CortexDB development agent workforce.
Standardized naming: CDB-{DEPT}-{ROLE}-{SEQ}

Departments: EXEC, ENG, QA, OPS, SEC, DOC
Hierarchy: Chief > Lead > Senior > Agent

Persistence-backed: all data survives server restarts.
"""

import time
import logging
from typing import Dict, List, Optional, TYPE_CHECKING
from dataclasses import dataclass, field, asdict
from enum import Enum

if TYPE_CHECKING:
    from cortexdb.superadmin.persistence import PersistenceStore

logger = logging.getLogger(__name__)


class Department(str, Enum):
    EXEC = "EXEC"
    ENG = "ENG"
    QA = "QA"
    OPS = "OPS"
    SEC = "SEC"
    DOC = "DOC"


class AgentTier(str, Enum):
    CHIEF = "CHIEF"
    LEAD = "LEAD"
    SENIOR = "SR"
    AGENT = "AGT"


class AgentState(str, Enum):
    ACTIVE = "active"
    IDLE = "idle"
    WORKING = "working"
    PAUSED = "paused"
    ERROR = "error"


@dataclass
class TeamAgent:
    agent_id: str
    name: str
    title: str
    department: Department
    tier: AgentTier
    reports_to: Optional[str]  # agent_id of supervisor
    responsibilities: List[str]
    skills: List[str]
    llm_provider: str = "ollama"
    llm_model: str = "llama3.1:8b"
    state: AgentState = AgentState.IDLE
    current_task: Optional[str] = None
    tasks_completed: int = 0
    tasks_failed: int = 0
    created_at: float = 0
    last_active: float = 0
    system_prompt: str = ""
    metadata: Dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Task:
    task_id: str
    title: str
    description: str
    assigned_to: Optional[str] = None  # agent_id
    created_by: str = "superadmin"
    status: str = "pending"  # pending, in_progress, review, completed, failed
    priority: str = "medium"  # critical, high, medium, low
    category: str = "general"  # bug, feature, enhancement, qa, docs, security, ops
    microservice: str = ""
    result: str = ""
    created_at: float = 0
    started_at: float = 0
    completed_at: float = 0
    metadata: Dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Instruction:
    instruction_id: str
    content: str
    response: str = ""
    agent_id: Optional[str] = None
    status: str = "pending"  # pending, processing, completed, failed
    provider: str = "ollama"
    model: str = ""
    created_at: float = 0
    completed_at: float = 0
    metadata: Dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


class AgentTeamManager:
    """Manages the CortexDB AI development workforce."""

    def __init__(self, persistence: "PersistenceStore" = None):
        self._agents: Dict[str, TeamAgent] = {}
        self._tasks: Dict[str, Task] = {}
        self._instructions: List[Instruction] = []
        self._task_counter = 0
        self._instruction_counter = 0
        self._initialized = False
        self._persistence = persistence

    def initialize(self):
        if self._initialized:
            return

        loaded = False
        if self._persistence:
            loaded = self._load_from_persistence()

        if not loaded:
            self._seed_org_chart()
            if self._persistence:
                self._save_agents()

        self._initialized = True

    def _load_from_persistence(self) -> bool:
        """Load state from persistence store. Returns True if data existed."""
        store = self._persistence

        # Load agents
        saved_agents = store.load("agents")
        if saved_agents and isinstance(saved_agents, dict) and len(saved_agents) > 0:
            for aid, adata in saved_agents.items():
                try:
                    self._agents[aid] = TeamAgent(**{
                        k: v for k, v in adata.items()
                        if k in TeamAgent.__dataclass_fields__
                    })
                except Exception as e:
                    logger.warning("Failed to load agent %s: %s", aid, e)
            logger.info("Loaded %d agents from persistence", len(self._agents))
        else:
            return False

        # Load tasks
        saved_tasks = store.load("tasks")
        if isinstance(saved_tasks, dict):
            for tid, tdata in saved_tasks.items():
                try:
                    self._tasks[tid] = Task(**{
                        k: v for k, v in tdata.items()
                        if k in Task.__dataclass_fields__
                    })
                except Exception:
                    pass
            self._task_counter = store.get_counter("task")

        # Load instructions
        saved_instrs = store.load("instructions")
        if isinstance(saved_instrs, list):
            for idata in saved_instrs:
                try:
                    self._instructions.append(Instruction(**{
                        k: v for k, v in idata.items()
                        if k in Instruction.__dataclass_fields__
                    }))
                except Exception:
                    pass
            self._instruction_counter = store.get_counter("instruction")

        logger.info("Loaded %d tasks, %d instructions from persistence",
                     len(self._tasks), len(self._instructions))
        return True

    def _save_agents(self):
        if self._persistence:
            self._persistence.save("agents", {
                aid: a.to_dict() for aid, a in self._agents.items()
            })

    def _save_tasks(self):
        if self._persistence:
            self._persistence.save("tasks", {
                tid: t.to_dict() for tid, t in self._tasks.items()
            })

    def _save_instructions(self):
        if self._persistence:
            self._persistence.save("instructions", [i.to_dict() for i in self._instructions])

    def _seed_org_chart(self):
        """Create the default organizational structure."""
        now = time.time()

        agents_def = [
            # Executive
            ("CDB-EXEC-CHIEF-001", "Atlas", "Chief Product Officer", Department.EXEC, AgentTier.CHIEF, None,
             ["Strategic product decisions", "Priority management", "Cross-department coordination", "Roadmap planning", "Release approval"],
             ["product-strategy", "decision-making", "coordination", "planning"],
             "You are Atlas, the Chief Product Officer of CortexDB. You oversee all development, coordinate departments, and make strategic decisions about the product roadmap."),

            # Engineering
            ("CDB-ENG-LEAD-001", "Forge", "Engineering Lead", Department.ENG, AgentTier.LEAD, "CDB-EXEC-CHIEF-001",
             ["Technical architecture decisions", "Code review oversight", "Sprint planning", "Engineering standards", "Mentor junior agents"],
             ["python", "typescript", "fastapi", "nextjs", "system-design", "code-review"],
             "You are Forge, the Engineering Lead. You oversee all engineering work on CortexDB, review architecture decisions, and ensure code quality across backend and frontend."),

            ("CDB-ENG-ARCH-001", "Blueprint", "Architecture Agent", Department.ENG, AgentTier.SENIOR, "CDB-ENG-LEAD-001",
             ["System design", "API design", "Database schema design", "Performance architecture", "Scalability planning"],
             ["system-design", "api-design", "database-design", "distributed-systems"],
             "You are Blueprint, the Architecture Agent. You design systems, APIs, and database schemas for CortexDB. Focus on scalability, performance, and clean architecture."),

            ("CDB-ENG-BACK-001", "Kernel", "Backend Engineer", Department.ENG, AgentTier.AGENT, "CDB-ENG-LEAD-001",
             ["Backend feature development", "API endpoint implementation", "Bug fixes in Python/FastAPI", "Database queries", "Integration development"],
             ["python", "fastapi", "postgresql", "redis", "async-programming"],
             "You are Kernel, the Backend Engineer. You implement features, fix bugs, and build API endpoints in the CortexDB Python/FastAPI backend."),

            ("CDB-ENG-FRONT-001", "Pixel", "Frontend Engineer", Department.ENG, AgentTier.AGENT, "CDB-ENG-LEAD-001",
             ["Dashboard UI development", "React component building", "State management", "Responsive design", "UX improvements"],
             ["typescript", "react", "nextjs", "tailwindcss", "zustand"],
             "You are Pixel, the Frontend Engineer. You build and improve the CortexDB dashboard using Next.js, React, and Tailwind CSS."),

            ("CDB-ENG-DATA-001", "Schema", "Data Engineer", Department.ENG, AgentTier.AGENT, "CDB-ENG-LEAD-001",
             ["Database migrations", "Schema design", "Data modeling", "Query optimization", "ETL pipelines"],
             ["postgresql", "sql", "data-modeling", "query-optimization", "migrations"],
             "You are Schema, the Data Engineer. You design database schemas, write migrations, optimize queries, and manage data models for CortexDB."),

            ("CDB-ENG-INTEG-001", "Bridge", "Integration Engineer", Department.ENG, AgentTier.AGENT, "CDB-ENG-LEAD-001",
             ["API integrations", "Third-party connectors", "MCP tool development", "A2A protocol work", "SDK development"],
             ["api-integration", "mcp", "a2a", "sdk-development", "webhooks"],
             "You are Bridge, the Integration Engineer. You build integrations, connectors, MCP tools, and A2A protocol handlers for CortexDB."),

            # QA
            ("CDB-QA-LEAD-001", "Guardian", "QA Lead", Department.QA, AgentTier.LEAD, "CDB-EXEC-CHIEF-001",
             ["Test strategy", "Quality standards", "Test automation oversight", "Release sign-off", "Bug triage"],
             ["test-strategy", "automation", "quality-assurance", "bug-triage"],
             "You are Guardian, the QA Lead. You define test strategy, manage quality standards, and oversee all testing for CortexDB."),

            ("CDB-QA-UNIT-001", "Prober", "Unit Test Agent", Department.QA, AgentTier.AGENT, "CDB-QA-LEAD-001",
             ["Unit test writing", "Test coverage analysis", "Mock/stub creation", "Regression testing"],
             ["pytest", "jest", "unit-testing", "mocking", "tdd"],
             "You are Prober, the Unit Test Agent. You write and maintain unit tests for CortexDB backend and frontend code."),

            ("CDB-QA-E2E-001", "Pathfinder", "E2E Test Agent", Department.QA, AgentTier.AGENT, "CDB-QA-LEAD-001",
             ["End-to-end test scenarios", "User flow testing", "API integration tests", "Cross-service testing"],
             ["e2e-testing", "playwright", "api-testing", "integration-testing"],
             "You are Pathfinder, the E2E Test Agent. You create end-to-end test scenarios that verify complete user flows across CortexDB."),

            ("CDB-QA-PERF-001", "Benchmark", "Performance Test Agent", Department.QA, AgentTier.AGENT, "CDB-QA-LEAD-001",
             ["Load testing", "Stress testing", "Performance benchmarking", "Bottleneck identification", "Latency profiling"],
             ["load-testing", "benchmarking", "profiling", "performance-optimization"],
             "You are Benchmark, the Performance Test Agent. You run load tests, stress tests, and identify performance bottlenecks in CortexDB."),

            ("CDB-QA-SEC-001", "Sentinel", "Security Test Agent", Department.QA, AgentTier.AGENT, "CDB-QA-LEAD-001",
             ["Security vulnerability scanning", "Penetration test planning", "OWASP compliance checks", "Dependency auditing"],
             ["security-testing", "owasp", "vulnerability-scanning", "penetration-testing"],
             "You are Sentinel, the Security Test Agent. You scan for vulnerabilities, verify OWASP compliance, and audit dependencies in CortexDB."),

            # Operations
            ("CDB-OPS-LEAD-001", "Conductor", "Operations Lead", Department.OPS, AgentTier.LEAD, "CDB-EXEC-CHIEF-001",
             ["Deployment orchestration", "Infrastructure management", "Incident response", "SLA monitoring", "Capacity planning"],
             ["devops", "docker", "ci-cd", "monitoring", "incident-response"],
             "You are Conductor, the Operations Lead. You manage deployments, infrastructure, and incident response for CortexDB."),

            ("CDB-OPS-DEPLOY-001", "Launcher", "Deployment Agent", Department.OPS, AgentTier.AGENT, "CDB-OPS-LEAD-001",
             ["CI/CD pipeline management", "Docker builds", "Release deployment", "Rollback procedures", "Environment management"],
             ["docker", "ci-cd", "github-actions", "deployment", "containerization"],
             "You are Launcher, the Deployment Agent. You manage CI/CD pipelines, Docker builds, and deployment processes for CortexDB."),

            ("CDB-OPS-MONITOR-001", "Watchdog", "Monitoring Agent", Department.OPS, AgentTier.AGENT, "CDB-OPS-LEAD-001",
             ["System health monitoring", "Alert management", "Log analysis", "Metric collection", "Anomaly detection"],
             ["monitoring", "alerting", "log-analysis", "prometheus", "grafana"],
             "You are Watchdog, the Monitoring Agent. You monitor system health, manage alerts, and analyze logs for CortexDB."),

            ("CDB-OPS-INFRA-001", "Terraform", "Infrastructure Agent", Department.OPS, AgentTier.AGENT, "CDB-OPS-LEAD-001",
             ["Infrastructure provisioning", "Scaling configuration", "Network setup", "Backup management", "Disaster recovery"],
             ["infrastructure", "scaling", "networking", "backup", "disaster-recovery"],
             "You are Terraform, the Infrastructure Agent. You manage infrastructure provisioning, scaling, and disaster recovery for CortexDB."),

            # Security
            ("CDB-SEC-LEAD-001", "Aegis", "Security Lead", Department.SEC, AgentTier.LEAD, "CDB-EXEC-CHIEF-001",
             ["Security policy enforcement", "Compliance management", "Threat assessment", "Security architecture review", "Incident investigation"],
             ["security-policy", "compliance", "threat-modeling", "security-architecture"],
             "You are Aegis, the Security Lead. You enforce security policies, manage compliance, and review security architecture for CortexDB."),

            ("CDB-SEC-AUDIT-001", "Inspector", "Audit Agent", Department.SEC, AgentTier.AGENT, "CDB-SEC-LEAD-001",
             ["Compliance auditing (SOC2, HIPAA, PCI)", "Security assessment reports", "Encryption verification", "Access control review"],
             ["compliance-audit", "soc2", "hipaa", "pci-dss", "encryption"],
             "You are Inspector, the Audit Agent. You perform compliance audits and security assessments for CortexDB."),

            ("CDB-SEC-GUARD-001", "Vault", "Guard Agent", Department.SEC, AgentTier.AGENT, "CDB-SEC-LEAD-001",
             ["Access control management", "Key rotation", "Encryption implementation", "Authentication hardening", "Secret management"],
             ["access-control", "encryption", "key-management", "authentication", "secrets"],
             "You are Vault, the Guard Agent. You manage encryption, access control, and secrets for CortexDB."),

            # Documentation
            ("CDB-DOC-LEAD-001", "Scribe", "Documentation Lead", Department.DOC, AgentTier.LEAD, "CDB-EXEC-CHIEF-001",
             ["Documentation strategy", "Content review", "Standards enforcement", "Knowledge base management", "Changelog maintenance"],
             ["technical-writing", "documentation", "knowledge-management"],
             "You are Scribe, the Documentation Lead. You manage all documentation and knowledge for CortexDB."),

            ("CDB-DOC-API-001", "Swagger", "API Documentation Agent", Department.DOC, AgentTier.AGENT, "CDB-DOC-LEAD-001",
             ["API reference documentation", "OpenAPI spec maintenance", "Endpoint examples", "SDK documentation"],
             ["openapi", "api-docs", "swagger", "sdk-docs"],
             "You are Swagger, the API Documentation Agent. You maintain API reference documentation and OpenAPI specs for CortexDB."),

            ("CDB-DOC-USER-001", "Guide", "User Documentation Agent", Department.DOC, AgentTier.AGENT, "CDB-DOC-LEAD-001",
             ["User guides", "Tutorial creation", "FAQ maintenance", "Onboarding documentation", "Feature documentation"],
             ["user-guides", "tutorials", "faq", "onboarding"],
             "You are Guide, the User Documentation Agent. You create user guides, tutorials, and onboarding docs for CortexDB."),

            ("CDB-DOC-ARCH-001", "Cartographer", "Architecture Doc Agent", Department.DOC, AgentTier.AGENT, "CDB-DOC-LEAD-001",
             ["Architecture decision records", "System diagrams", "Design documents", "Technical specs", "Runbook creation"],
             ["adr", "system-diagrams", "design-docs", "runbooks"],
             "You are Cartographer, the Architecture Doc Agent. You document system architecture, create design docs, and maintain ADRs for CortexDB."),
        ]

        for (aid, name, title, dept, tier, reports_to, responsibilities, skills, system_prompt) in agents_def:
            self._agents[aid] = TeamAgent(
                agent_id=aid, name=name, title=title, department=dept, tier=tier,
                reports_to=reports_to, responsibilities=responsibilities, skills=skills,
                system_prompt=system_prompt, created_at=now, state=AgentState.ACTIVE,
            )

    def add_agent(self, agent_data: dict):
        """Add a new agent from a dict (used by templates/cloning)."""
        aid = agent_data.get("agent_id", "")
        if not aid:
            return
        fields = {k: v for k, v in agent_data.items() if k in TeamAgent.__dataclass_fields__}
        fields.setdefault("created_at", time.time())
        fields.setdefault("state", AgentState.ACTIVE)
        self._agents[aid] = TeamAgent(**fields)
        self._save_agents()
        logger.info("Agent added: %s", aid)

    # ── Agent CRUD ──

    def get_all_agents(self) -> List[dict]:
        return [a.to_dict() for a in self._agents.values()]

    def get_agent(self, agent_id: str) -> Optional[dict]:
        a = self._agents.get(agent_id)
        return a.to_dict() if a else None

    def update_agent(self, agent_id: str, updates: dict) -> Optional[dict]:
        a = self._agents.get(agent_id)
        if not a:
            return None
        for key, val in updates.items():
            if hasattr(a, key) and key not in ("agent_id", "created_at"):
                setattr(a, key, val)
        self._save_agents()
        return a.to_dict()

    def get_org_chart(self) -> dict:
        """Build hierarchical org chart."""
        def build_tree(parent_id: Optional[str]) -> List[dict]:
            children = []
            for a in self._agents.values():
                if a.reports_to == parent_id:
                    node = {
                        "agent_id": a.agent_id,
                        "name": a.name,
                        "title": a.title,
                        "department": a.department,
                        "tier": a.tier,
                        "state": a.state,
                        "llm_provider": a.llm_provider,
                        "llm_model": a.llm_model,
                        "children": build_tree(a.agent_id),
                    }
                    children.append(node)
            return children

        return {
            "root": build_tree(None),
            "departments": {d.value: self.get_department(d.value) for d in Department},
            "total_agents": len(self._agents),
        }

    def get_department(self, dept: str) -> dict:
        agents = [a for a in self._agents.values() if a.department == dept]
        return {
            "department": dept,
            "agent_count": len(agents),
            "agents": [a.to_dict() for a in agents],
            "lead": next((a.agent_id for a in agents if a.tier in (AgentTier.LEAD, AgentTier.CHIEF)), None),
        }

    # ── Task Management ──

    def create_task(self, title: str, description: str, assigned_to: str = None,
                    priority: str = "medium", category: str = "general",
                    microservice: str = "") -> dict:
        if self._persistence:
            self._task_counter = self._persistence.increment_counter("task")
        else:
            self._task_counter += 1
        task_id = f"TSK-{self._task_counter:04d}"
        task = Task(
            task_id=task_id, title=title, description=description,
            assigned_to=assigned_to, priority=priority, category=category,
            microservice=microservice, created_at=time.time(),
        )
        if assigned_to and assigned_to in self._agents:
            task.status = "in_progress"
            task.started_at = time.time()
            self._agents[assigned_to].state = AgentState.WORKING
            self._agents[assigned_to].current_task = task_id
            self._save_agents()
        self._tasks[task_id] = task
        self._save_tasks()

        if self._persistence:
            self._persistence.audit("task_created", "task", task_id,
                                    {"title": title, "assigned_to": assigned_to, "priority": priority})
        return task.to_dict()

    def get_all_tasks(self, status: str = None) -> List[dict]:
        tasks = list(self._tasks.values())
        if status:
            tasks = [t for t in tasks if t.status == status]
        return [t.to_dict() for t in sorted(tasks, key=lambda x: -x.created_at)]

    def get_task(self, task_id: str) -> Optional[dict]:
        t = self._tasks.get(task_id)
        return t.to_dict() if t else None

    def update_task(self, task_id: str, updates: dict) -> Optional[dict]:
        t = self._tasks.get(task_id)
        if not t:
            return None
        for key, val in updates.items():
            if hasattr(t, key) and key not in ("task_id", "created_at"):
                setattr(t, key, val)
        if updates.get("status") == "completed":
            t.completed_at = time.time()
            if t.assigned_to and t.assigned_to in self._agents:
                agent = self._agents[t.assigned_to]
                agent.tasks_completed += 1
                agent.state = AgentState.IDLE
                agent.current_task = None
                self._save_agents()
        self._save_tasks()
        return t.to_dict()

    # ── Instructions / Conversation ──

    def add_instruction(self, content: str, agent_id: str = None,
                        provider: str = "ollama", model: str = "") -> dict:
        if self._persistence:
            self._instruction_counter = self._persistence.increment_counter("instruction")
        else:
            self._instruction_counter += 1
        instr = Instruction(
            instruction_id=f"INS-{self._instruction_counter:04d}",
            content=content, agent_id=agent_id, provider=provider,
            model=model, created_at=time.time(),
        )
        self._instructions.append(instr)
        self._save_instructions()
        return instr.to_dict()

    def update_instruction(self, instruction_id: str, response: str,
                           status: str = "completed") -> Optional[dict]:
        for instr in self._instructions:
            if instr.instruction_id == instruction_id:
                instr.response = response
                instr.status = status
                instr.completed_at = time.time()
                self._save_instructions()
                return instr.to_dict()
        return None

    def get_instructions(self, agent_id: str = None, limit: int = 50) -> List[dict]:
        instrs = self._instructions
        if agent_id:
            instrs = [i for i in instrs if i.agent_id == agent_id]
        return [i.to_dict() for i in sorted(instrs, key=lambda x: -x.created_at)[:limit]]

    def get_summary(self) -> dict:
        agents = list(self._agents.values())
        tasks = list(self._tasks.values())
        return {
            "total_agents": len(agents),
            "agents_working": sum(1 for a in agents if a.state == AgentState.WORKING),
            "agents_active": sum(1 for a in agents if a.state == AgentState.ACTIVE),
            "agents_idle": sum(1 for a in agents if a.state == AgentState.IDLE),
            "total_tasks": len(tasks),
            "tasks_pending": sum(1 for t in tasks if t.status == "pending"),
            "tasks_in_progress": sum(1 for t in tasks if t.status == "in_progress"),
            "tasks_completed": sum(1 for t in tasks if t.status == "completed"),
            "total_instructions": len(self._instructions),
            "departments": list(set(a.department for a in agents)),
        }

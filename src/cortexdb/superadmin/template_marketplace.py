"""
Agent Template Marketplace — Community-contributed agent templates and blueprints.

Browse and install pre-built agent templates, workflow blueprints, and skill packs
from a curated marketplace. Templates can be rated, searched, and filtered by category.

Database: data/superadmin.db (shared with other superadmin modules)
Table: community_templates
"""

import json
import os
import sqlite3
import uuid
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from cortexdb.superadmin.agent_team import AgentTeamManager
    from cortexdb.superadmin.persistence import PersistenceStore

logger = logging.getLogger("cortexdb.template_marketplace")

DEFAULT_DB_PATH = os.path.join("data", "superadmin.db")

# ── Seed templates ────────────────────────────────────────────────────

SEED_TEMPLATES: List[Dict[str, Any]] = [
    {
        "name": "Data Analyst Agent",
        "description": "Analyzes datasets, generates statistical reports, identifies trends, and produces visualizations. Skilled in SQL, data profiling, and anomaly detection.",
        "author": "CortexDB Team",
        "category": "analytics",
        "tags": ["data", "analytics", "reports", "sql", "statistics"],
        "version": "1.0.0",
        "featured": True,
        "template_data": {
            "agent_name": "DataAnalyst",
            "title": "Senior Data Analyst",
            "department": "ENG",
            "responsibilities": [
                "Analyze datasets and generate statistical summaries",
                "Identify trends, outliers, and anomalies in data",
                "Generate CortexQL queries for ad-hoc analysis",
                "Produce periodic data quality reports",
                "Recommend data pipeline improvements",
            ],
            "skills": ["sql", "statistics", "data-profiling", "visualization", "anomaly-detection"],
            "llm_provider": "claude",
            "model": "claude-sonnet-4-20250514",
            "system_prompt": (
                "You are a senior data analyst agent. You excel at analyzing datasets, "
                "writing efficient queries, identifying statistical patterns, and communicating "
                "findings clearly. Always provide data-backed insights with confidence intervals "
                "where appropriate."
            ),
        },
    },
    {
        "name": "Customer Support Agent",
        "description": "Handles customer tickets, answers FAQs, escalates complex issues, and tracks resolution metrics. Trained on common support workflows.",
        "author": "CortexDB Team",
        "category": "support",
        "tags": ["support", "tickets", "faq", "customer-service", "escalation"],
        "version": "1.0.0",
        "featured": True,
        "template_data": {
            "agent_name": "SupportAgent",
            "title": "Customer Support Specialist",
            "department": "OPS",
            "responsibilities": [
                "Respond to customer support tickets within SLA",
                "Answer frequently asked questions from knowledge base",
                "Escalate complex or high-priority issues to human agents",
                "Track resolution times and satisfaction metrics",
                "Update the FAQ knowledge base with new solutions",
            ],
            "skills": ["customer-service", "ticket-management", "knowledge-base", "escalation", "sla-tracking"],
            "llm_provider": "ollama",
            "model": "llama3.1:8b",
            "system_prompt": (
                "You are a customer support specialist. Be empathetic, clear, and solution-oriented. "
                "Always acknowledge the customer's issue before providing a solution. Escalate to a "
                "human agent if you cannot resolve the issue within 3 attempts."
            ),
        },
    },
    {
        "name": "Security Auditor Agent",
        "description": "Scans for vulnerabilities, checks compliance with security policies, reviews access controls, and generates audit reports.",
        "author": "CortexDB Team",
        "category": "security",
        "tags": ["security", "audit", "compliance", "vulnerability", "access-control"],
        "version": "1.0.0",
        "featured": True,
        "template_data": {
            "agent_name": "SecurityAuditor",
            "title": "Security Auditor",
            "department": "SEC",
            "responsibilities": [
                "Scan systems for known vulnerabilities and misconfigurations",
                "Verify compliance with security policies and standards",
                "Review agent access controls and permission boundaries",
                "Generate periodic security audit reports",
                "Flag suspicious patterns in agent activity logs",
            ],
            "skills": ["vulnerability-scanning", "compliance-audit", "access-review", "threat-detection", "report-generation"],
            "llm_provider": "claude",
            "model": "claude-sonnet-4-20250514",
            "system_prompt": (
                "You are a security auditor agent. You methodically check systems for vulnerabilities, "
                "verify compliance with established policies, and produce detailed audit reports. "
                "Always err on the side of caution and flag potential issues even if uncertain."
            ),
        },
    },
    {
        "name": "Content Writer Agent",
        "description": "Writes blog posts, technical documentation, release notes, and marketing copy. Maintains consistent tone and style guidelines.",
        "author": "CortexDB Team",
        "category": "content",
        "tags": ["content", "writing", "documentation", "blog", "copywriting"],
        "version": "1.0.0",
        "featured": False,
        "template_data": {
            "agent_name": "ContentWriter",
            "title": "Technical Content Writer",
            "department": "DOC",
            "responsibilities": [
                "Write technical blog posts and tutorials",
                "Create and maintain API documentation",
                "Draft release notes and changelogs",
                "Produce marketing copy for product features",
                "Ensure consistency with brand style guidelines",
            ],
            "skills": ["technical-writing", "documentation", "copywriting", "markdown", "style-guide"],
            "llm_provider": "claude",
            "model": "claude-sonnet-4-20250514",
            "system_prompt": (
                "You are a technical content writer. Write clearly, concisely, and accurately. "
                "Use active voice, short paragraphs, and include code examples where relevant. "
                "Follow the project style guide and maintain a professional but approachable tone."
            ),
        },
    },
    {
        "name": "DevOps Engineer Agent",
        "description": "Manages deployments, monitors infrastructure health, configures CI/CD pipelines, and handles incident response.",
        "author": "CortexDB Team",
        "category": "devops",
        "tags": ["devops", "deployment", "infrastructure", "ci-cd", "monitoring"],
        "version": "1.0.0",
        "featured": True,
        "template_data": {
            "agent_name": "DevOpsEngineer",
            "title": "DevOps Engineer",
            "department": "OPS",
            "responsibilities": [
                "Manage deployment pipelines and release processes",
                "Monitor infrastructure health and resource utilization",
                "Configure and maintain CI/CD pipelines",
                "Respond to infrastructure incidents and alerts",
                "Optimize container orchestration and scaling policies",
            ],
            "skills": ["docker", "kubernetes", "ci-cd", "monitoring", "incident-response", "terraform"],
            "llm_provider": "ollama",
            "model": "llama3.1:8b",
            "system_prompt": (
                "You are a DevOps engineer agent. Focus on reliability, automation, and observability. "
                "When handling incidents, follow the incident response playbook: detect, triage, mitigate, "
                "resolve, and post-mortem. Always prefer infrastructure-as-code approaches."
            ),
        },
    },
    {
        "name": "Research Assistant Agent",
        "description": "Conducts literature reviews, summarizes papers, identifies key findings, and maintains a research knowledge base.",
        "author": "CortexDB Team",
        "category": "research",
        "tags": ["research", "literature-review", "summarization", "knowledge-base", "academia"],
        "version": "1.0.0",
        "featured": False,
        "template_data": {
            "agent_name": "ResearchAssistant",
            "title": "Research Assistant",
            "department": "ENG",
            "responsibilities": [
                "Conduct literature reviews on specified topics",
                "Summarize research papers and extract key findings",
                "Maintain a structured research knowledge base",
                "Identify research gaps and propose new directions",
                "Cross-reference findings across multiple sources",
            ],
            "skills": ["literature-review", "summarization", "knowledge-management", "citation-tracking", "critical-analysis"],
            "llm_provider": "claude",
            "model": "claude-sonnet-4-20250514",
            "system_prompt": (
                "You are a research assistant agent. Be thorough, objective, and precise. "
                "Always cite sources, distinguish between established facts and hypotheses, "
                "and clearly state the limitations of any findings."
            ),
        },
    },
    {
        "name": "Sales Intelligence Agent",
        "description": "Scores leads, analyzes market trends, generates competitive intelligence reports, and identifies revenue opportunities.",
        "author": "CortexDB Team",
        "category": "sales",
        "tags": ["sales", "leads", "market-analysis", "competitive-intelligence", "revenue"],
        "version": "1.0.0",
        "featured": False,
        "template_data": {
            "agent_name": "SalesIntelligence",
            "title": "Sales Intelligence Analyst",
            "department": "ENG",
            "responsibilities": [
                "Score and prioritize inbound leads based on fit criteria",
                "Analyze market trends and competitive landscape",
                "Generate weekly competitive intelligence briefs",
                "Identify upsell and cross-sell opportunities",
                "Track sales pipeline health metrics",
            ],
            "skills": ["lead-scoring", "market-analysis", "competitive-intelligence", "forecasting", "crm"],
            "llm_provider": "ollama",
            "model": "llama3.1:8b",
            "system_prompt": (
                "You are a sales intelligence analyst. Focus on actionable insights that drive revenue. "
                "Quantify opportunities where possible, prioritize by expected impact, "
                "and always consider the competitive context."
            ),
        },
    },
    {
        "name": "QA Test Agent",
        "description": "Generates test cases from specifications, executes test suites, reports coverage gaps, and tracks regression issues.",
        "author": "CortexDB Team",
        "category": "qa",
        "tags": ["qa", "testing", "test-cases", "coverage", "regression"],
        "version": "1.0.0",
        "featured": True,
        "template_data": {
            "agent_name": "QATester",
            "title": "QA Test Engineer",
            "department": "QA",
            "responsibilities": [
                "Generate test cases from feature specifications",
                "Execute automated test suites and report results",
                "Identify test coverage gaps and recommend improvements",
                "Track and triage regression issues",
                "Maintain the test case knowledge base",
            ],
            "skills": ["test-generation", "test-automation", "coverage-analysis", "regression-testing", "bug-triage"],
            "llm_provider": "claude",
            "model": "claude-sonnet-4-20250514",
            "system_prompt": (
                "You are a QA test engineer agent. Be meticulous and systematic. "
                "Write test cases that cover happy paths, edge cases, and error conditions. "
                "Prioritize tests by risk and business impact. Report bugs with clear "
                "reproduction steps."
            ),
        },
    },
    {
        "name": "Financial Analyst Agent",
        "description": "Tracks budgets, generates financial forecasts, analyzes cost trends, and produces variance reports.",
        "author": "CortexDB Team",
        "category": "finance",
        "tags": ["finance", "budget", "forecasting", "cost-analysis", "variance"],
        "version": "1.0.0",
        "featured": False,
        "template_data": {
            "agent_name": "FinancialAnalyst",
            "title": "Financial Analyst",
            "department": "ENG",
            "responsibilities": [
                "Track departmental budgets and expenditures",
                "Generate monthly financial forecasts",
                "Analyze cost trends and identify savings opportunities",
                "Produce budget variance reports with explanations",
                "Monitor LLM API costs and resource utilization",
            ],
            "skills": ["budgeting", "forecasting", "cost-analysis", "variance-analysis", "financial-reporting"],
            "llm_provider": "ollama",
            "model": "llama3.1:8b",
            "system_prompt": (
                "You are a financial analyst agent. Be precise with numbers, always show your "
                "calculations, and present data in clear tabular formats. Flag any variances "
                "exceeding 10% from forecast with root-cause analysis."
            ),
        },
    },
    {
        "name": "HR Recruiter Agent",
        "description": "Screens resumes, schedules interviews, manages candidate pipelines, and tracks recruiting metrics.",
        "author": "CortexDB Team",
        "category": "hr",
        "tags": ["hr", "recruiting", "resume-screening", "interviews", "pipeline"],
        "version": "1.0.0",
        "featured": False,
        "template_data": {
            "agent_name": "HRRecruiter",
            "title": "Talent Acquisition Specialist",
            "department": "OPS",
            "responsibilities": [
                "Screen resumes against job requirement criteria",
                "Schedule and coordinate interview loops",
                "Manage the candidate pipeline through all stages",
                "Track recruiting metrics (time-to-fill, conversion rates)",
                "Generate weekly hiring pipeline reports",
            ],
            "skills": ["resume-screening", "interview-scheduling", "pipeline-management", "metrics-tracking", "candidate-communication"],
            "llm_provider": "ollama",
            "model": "llama3.1:8b",
            "system_prompt": (
                "You are a talent acquisition specialist agent. Evaluate candidates objectively "
                "based on skills and experience fit. Maintain a fair and structured process. "
                "Communicate clearly with candidates and hiring managers about timelines."
            ),
        },
    },
    {
        "name": "Legal Compliance Agent",
        "description": "Reviews contracts for risk clauses, monitors regulatory changes, ensures policy compliance, and generates compliance reports.",
        "author": "CortexDB Team",
        "category": "legal",
        "tags": ["legal", "compliance", "contracts", "regulation", "risk"],
        "version": "1.0.0",
        "featured": False,
        "template_data": {
            "agent_name": "LegalCompliance",
            "title": "Compliance Officer",
            "department": "SEC",
            "responsibilities": [
                "Review contracts for unfavorable or risky clauses",
                "Monitor regulatory changes relevant to operations",
                "Ensure agent activities comply with data protection policies",
                "Generate quarterly compliance audit reports",
                "Maintain a regulatory change log and impact assessments",
            ],
            "skills": ["contract-review", "regulatory-monitoring", "compliance-audit", "risk-assessment", "policy-enforcement"],
            "llm_provider": "claude",
            "model": "claude-sonnet-4-20250514",
            "system_prompt": (
                "You are a legal compliance officer agent. Be thorough and conservative in risk "
                "assessment. Always flag potential compliance issues even if they seem minor. "
                "Reference specific regulations and policies in your analysis. Never provide "
                "legal advice — recommend consulting legal counsel for complex matters."
            ),
        },
    },
    {
        "name": "Marketing Strategist Agent",
        "description": "Analyzes campaign performance, designs A/B tests, generates marketing reports, and identifies audience segments.",
        "author": "CortexDB Team",
        "category": "marketing",
        "tags": ["marketing", "campaigns", "a-b-testing", "analytics", "segmentation"],
        "version": "1.0.0",
        "featured": False,
        "template_data": {
            "agent_name": "MarketingStrategist",
            "title": "Marketing Strategist",
            "department": "ENG",
            "responsibilities": [
                "Analyze marketing campaign performance metrics",
                "Design and evaluate A/B test experiments",
                "Generate weekly marketing analytics reports",
                "Identify high-value audience segments",
                "Recommend content and channel optimization strategies",
            ],
            "skills": ["campaign-analysis", "ab-testing", "audience-segmentation", "content-strategy", "marketing-analytics"],
            "llm_provider": "ollama",
            "model": "llama3.1:8b",
            "system_prompt": (
                "You are a marketing strategist agent. Focus on data-driven decisions. "
                "Always tie recommendations to measurable KPIs. When proposing A/B tests, "
                "specify the hypothesis, control, variant, and minimum sample size."
            ),
        },
    },
]


class TemplateMarketplace:
    """Community template marketplace with browsing, installation, and rating support.

    Provides a curated collection of agent templates that can be browsed,
    searched, installed, rated, and published. Templates are stored in SQLite
    and seeded with defaults on first initialization.
    """

    def __init__(
        self,
        agent_team: "AgentTeamManager",
        persistence_store: "PersistenceStore",
        db_path: str = DEFAULT_DB_PATH,
    ):
        self._team = agent_team
        self._store = persistence_store
        self.db_path = db_path
        self.db: Optional[sqlite3.Connection] = None
        self._init_db()

    # ── Database setup ────────────────────────────────────────────────

    def _get_connection(self) -> sqlite3.Connection:
        """Get or create a SQLite connection with row factory."""
        if self.db is None or not self._connection_alive():
            db_dir = os.path.dirname(self.db_path)
            if db_dir:
                os.makedirs(db_dir, exist_ok=True)
            self.db = sqlite3.connect(self.db_path, timeout=10.0)
            self.db.row_factory = sqlite3.Row
            self.db.execute("PRAGMA journal_mode=WAL")
            self.db.execute("PRAGMA foreign_keys=ON")
        return self.db

    def _connection_alive(self) -> bool:
        """Check if the current connection is still usable."""
        try:
            self.db.execute("SELECT 1")
            return True
        except Exception:
            return False

    def _init_db(self) -> None:
        """Seed defaults. Table 'community_templates' is managed by the SQLite
        migration system (see migrations.py v5)."""
        conn = self._get_connection()

        # Seed defaults if table is empty
        row = conn.execute("SELECT COUNT(*) AS cnt FROM community_templates").fetchone()
        if row["cnt"] == 0:
            self._seed_defaults(conn)

    def _seed_defaults(self, conn: sqlite3.Connection) -> None:
        """Insert the 12 default templates."""
        now = datetime.now(timezone.utc).isoformat()
        for tmpl in SEED_TEMPLATES:
            template_id = str(uuid.uuid4())
            conn.execute(
                """
                INSERT INTO community_templates
                    (id, name, description, author, category, tags, template_data,
                     version, downloads, rating, ratings_count, featured, published_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    template_id,
                    tmpl["name"],
                    tmpl["description"],
                    tmpl["author"],
                    tmpl["category"],
                    json.dumps(tmpl["tags"]),
                    json.dumps(tmpl["template_data"]),
                    tmpl["version"],
                    0,
                    0.0,
                    0,
                    1 if tmpl.get("featured") else 0,
                    now,
                    now,
                ),
            )
        conn.commit()
        logger.info("Seeded %d default community templates", len(SEED_TEMPLATES))

    # ── Template row helpers ──────────────────────────────────────────

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> dict:
        """Convert a database row to a template dict."""
        return {
            "id": row["id"],
            "name": row["name"],
            "description": row["description"],
            "author": row["author"],
            "category": row["category"],
            "tags": json.loads(row["tags"]),
            "template_data": json.loads(row["template_data"]),
            "version": row["version"],
            "downloads": row["downloads"],
            "rating": round(row["rating"], 2),
            "ratings_count": row["ratings_count"],
            "featured": bool(row["featured"]),
            "published_at": row["published_at"],
            "updated_at": row["updated_at"],
        }

    # ── Query methods ─────────────────────────────────────────────────

    def list_templates(
        self,
        category: str = None,
        sort_by: str = "downloads",
        search: str = None,
        featured_only: bool = False,
    ) -> list:
        """List templates with optional filtering and sorting.

        Args:
            category: Filter by category (e.g. 'analytics', 'security').
            sort_by: Sort field — 'downloads', 'rating', 'name', 'published_at'.
            search: Search term to match against name, description, and tags.
            featured_only: If True, return only featured templates.

        Returns:
            List of template dicts.
        """
        conn = self._get_connection()
        clauses: List[str] = []
        params: List[Any] = []

        if category:
            clauses.append("category = ?")
            params.append(category)
        if featured_only:
            clauses.append("featured = 1")
        if search:
            clauses.append("(name LIKE ? OR description LIKE ? OR tags LIKE ?)")
            pattern = f"%{search}%"
            params.extend([pattern, pattern, pattern])

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""

        # Validate sort field
        valid_sorts = {"downloads": "downloads DESC", "rating": "rating DESC",
                       "name": "name ASC", "published_at": "published_at DESC"}
        order = valid_sorts.get(sort_by, "downloads DESC")

        query = f"SELECT * FROM community_templates {where} ORDER BY {order}"
        rows = conn.execute(query, params).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def get_template(self, template_id: str) -> dict:
        """Get a single template by ID.

        Args:
            template_id: The template to retrieve.

        Returns:
            Template dict, or error dict if not found.
        """
        conn = self._get_connection()
        row = conn.execute(
            "SELECT * FROM community_templates WHERE id = ?", (template_id,)
        ).fetchone()

        if row is None:
            return {"error": "Template not found", "template_id": template_id}
        return self._row_to_dict(row)

    def get_featured(self) -> list:
        """Get all featured templates.

        Returns:
            List of featured template dicts.
        """
        return self.list_templates(featured_only=True, sort_by="downloads")

    def get_categories(self) -> list:
        """List all categories with template counts.

        Returns:
            List of dicts with category name and count.
        """
        conn = self._get_connection()
        rows = conn.execute(
            """
            SELECT category, COUNT(*) AS count
            FROM community_templates
            GROUP BY category
            ORDER BY count DESC
            """
        ).fetchall()
        return [{"category": r["category"], "count": r["count"]} for r in rows]

    # ── Install ───────────────────────────────────────────────────────

    def install_template(self, template_id: str) -> dict:
        """Install a template by creating an agent from its template data.

        Creates a new agent in the agent team based on the template's
        configuration and increments the template's download count.

        Args:
            template_id: The template to install.

        Returns:
            Dict with success status and the created agent's ID, or error.
        """
        template = self.get_template(template_id)
        if "error" in template:
            return template

        data = template["template_data"]
        agent_name = data.get("agent_name", "TemplateAgent")
        department = data.get("department", "ENG")

        # Create agent via agent team manager
        try:
            if hasattr(self._team, "hire_agent"):
                result = self._team.hire_agent(
                    name=agent_name,
                    title=data.get("title", "Agent"),
                    department=department,
                    responsibilities=data.get("responsibilities", []),
                    skills=data.get("skills", []),
                    llm_provider=data.get("llm_provider", "ollama"),
                    llm_model=data.get("model", "llama3.1:8b"),
                    system_prompt=data.get("system_prompt", ""),
                )
                agent_id = result if isinstance(result, str) else (
                    result.get("agent_id") if isinstance(result, dict) else str(result)
                )
            elif hasattr(self._team, "add_agent"):
                agent_id = self._team.add_agent(
                    name=agent_name,
                    title=data.get("title", "Agent"),
                    department=department,
                    responsibilities=data.get("responsibilities", []),
                    skills=data.get("skills", []),
                )
            else:
                return {"error": "Agent team does not support agent creation"}
        except Exception as e:
            logger.error("Failed to install template %s: %s", template_id, e)
            return {"error": f"Agent creation failed: {e}", "template_id": template_id}

        # Increment download count
        now = datetime.now(timezone.utc).isoformat()
        conn = self._get_connection()
        conn.execute(
            "UPDATE community_templates SET downloads = downloads + 1, updated_at = ? WHERE id = ?",
            (now, template_id),
        )
        conn.commit()

        logger.info(
            "Installed template '%s' (id=%s) as agent %s",
            template["name"], template_id, agent_id,
        )

        return {
            "success": True,
            "template_id": template_id,
            "template_name": template["name"],
            "agent_id": agent_id,
        }

    # ── Rating ────────────────────────────────────────────────────────

    def rate_template(self, template_id: str, rating: int) -> dict:
        """Rate a template on a 1-5 star scale.

        Updates the template's rolling average rating.

        Args:
            template_id: The template to rate.
            rating: Integer rating from 1 to 5.

        Returns:
            Dict with success status and updated rating info.
        """
        if not isinstance(rating, int) or rating < 1 or rating > 5:
            return {"error": "Rating must be an integer between 1 and 5"}

        conn = self._get_connection()
        row = conn.execute(
            "SELECT rating, ratings_count FROM community_templates WHERE id = ?",
            (template_id,),
        ).fetchone()

        if row is None:
            return {"error": "Template not found", "template_id": template_id}

        old_rating = row["rating"]
        old_count = row["ratings_count"]

        # Calculate new rolling average
        new_count = old_count + 1
        new_rating = ((old_rating * old_count) + rating) / new_count

        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            """
            UPDATE community_templates
            SET rating = ?, ratings_count = ?, updated_at = ?
            WHERE id = ?
            """,
            (new_rating, new_count, now, template_id),
        )
        conn.commit()

        logger.info(
            "Rated template %s: %d stars (new avg: %.2f from %d ratings)",
            template_id, rating, new_rating, new_count,
        )

        return {
            "success": True,
            "template_id": template_id,
            "rating": round(new_rating, 2),
            "ratings_count": new_count,
        }

    # ── Publish ───────────────────────────────────────────────────────

    def publish_template(self, template_data: dict) -> dict:
        """Publish a new template to the marketplace.

        Args:
            template_data: Dict with required keys: name, description, category,
                template_data. Optional: author, tags, version.

        Returns:
            Dict with success status and new template ID.
        """
        # Validate required fields
        required = ["name", "description", "category", "template_data"]
        missing = [f for f in required if f not in template_data]
        if missing:
            return {"error": f"Missing required fields: {', '.join(missing)}"}

        name = template_data["name"]
        description = template_data["description"]
        category = template_data["category"]
        inner_data = template_data["template_data"]

        # Validate template_data structure
        if not isinstance(inner_data, dict):
            return {"error": "template_data must be a dict"}

        template_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        conn = self._get_connection()
        conn.execute(
            """
            INSERT INTO community_templates
                (id, name, description, author, category, tags, template_data,
                 version, downloads, rating, ratings_count, featured, published_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, 0.0, 0, 0, ?, ?)
            """,
            (
                template_id,
                name,
                description,
                template_data.get("author", "Community"),
                category,
                json.dumps(template_data.get("tags", [])),
                json.dumps(inner_data),
                template_data.get("version", "1.0.0"),
                now,
                now,
            ),
        )
        conn.commit()

        logger.info("Published new template '%s' (id=%s, category=%s)", name, template_id, category)

        return {
            "success": True,
            "template_id": template_id,
            "name": name,
            "category": category,
        }

    # ── Stats ─────────────────────────────────────────────────────────

    def get_stats(self) -> dict:
        """Get marketplace statistics.

        Returns:
            Dict with total templates, total downloads, average rating,
            and category breakdown.
        """
        conn = self._get_connection()

        total_row = conn.execute(
            "SELECT COUNT(*) AS cnt FROM community_templates"
        ).fetchone()
        total = total_row["cnt"] if total_row else 0

        downloads_row = conn.execute(
            "SELECT COALESCE(SUM(downloads), 0) AS total FROM community_templates"
        ).fetchone()
        total_downloads = downloads_row["total"] if downloads_row else 0

        rated_row = conn.execute(
            """
            SELECT COALESCE(AVG(rating), 0.0) AS avg_rating,
                   COALESCE(SUM(ratings_count), 0) AS total_ratings
            FROM community_templates
            WHERE ratings_count > 0
            """
        ).fetchone()
        avg_rating = round(rated_row["avg_rating"], 2) if rated_row else 0.0
        total_ratings = rated_row["total_ratings"] if rated_row else 0

        featured_row = conn.execute(
            "SELECT COUNT(*) AS cnt FROM community_templates WHERE featured = 1"
        ).fetchone()
        featured_count = featured_row["cnt"] if featured_row else 0

        return {
            "total_templates": total,
            "total_downloads": total_downloads,
            "avg_rating": avg_rating,
            "total_ratings": total_ratings,
            "featured_count": featured_count,
            "categories": self.get_categories(),
        }

    # ── Cleanup ───────────────────────────────────────────────────────

    def close(self) -> None:
        """Close the database connection."""
        if self.db is not None:
            try:
                self.db.close()
            except Exception:
                pass
            self.db = None

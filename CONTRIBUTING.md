# Contributing to CortexDB™

Thank you for your interest in contributing to CortexDB — an AI Agent Data Infrastructure layer that coordinates PostgreSQL, Redis, and Qdrant through a single API. CortexDB provides write fan-out, semantic caching, cross-engine queries, and agent-facing tool interfaces (MCP, A2A) on top of existing database engines.

---

## Code of Conduct

Be respectful, constructive, and professional.

---

## Getting Started

### Prerequisites

- Python 3.11+
- Docker & Docker Compose
- Git

### Development Setup

```bash
# Clone
git clone https://github.com/nirlab/cortexdb.git
cd cortexdb

# Create virtual environment
python -m venv venv
source venv/bin/activate   # Linux/Mac
venv\Scripts\activate      # Windows

# Install dependencies
pip install -r requirements.txt

# Start infrastructure
docker compose up -d relational-core memory-core stream-core vector-core

# Run the API server locally
uvicorn cortexdb.server:app --host 0.0.0.0 --port 5400 --reload
```

### Running Tests

```bash
# Unit tests
pytest tests/ -v

# Integration tests (requires Docker services)
pytest tests/integration/ -v

# Compliance tests
pytest tests/compliance/ -v
```

---

## Project Structure

```
cortexdb/
├── cortexdb/              # Main package
│   ├── core/              # Database core (router, cache, parser)
│   ├── engines/           # 7 storage engine adapters
│   ├── cortexgraph/       # Customer intelligence
│   ├── scale/             # Sharding, replication, indexing
│   ├── compliance/        # FedRAMP, SOC2, HIPAA, PCI
│   ├── tenant/            # Multi-tenancy
│   ├── rate_limit/        # Rate limiting
│   ├── mcp/               # MCP server for AI agents
│   ├── a2a/               # Agent-to-Agent protocol
│   ├── grid/              # Self-healing grid
│   ├── heartbeat/         # Health monitoring
│   ├── asa/               # Standards enforcement
│   └── observability/     # Tracing + metrics
├── init-scripts/          # SQL schema files
├── docs/                  # Documentation
└── tests/                 # Test suite
```

---

## Coding Standards

### Python Style

- Follow PEP 8
- Use type hints for function signatures
- Docstrings for public classes and methods
- Maximum line length: 100 characters
- Use `async/await` for all I/O operations

### Naming Conventions

- Files: `snake_case.py`
- Classes: `PascalCase`
- Functions: `snake_case`
- Constants: `UPPER_SNAKE_CASE`
- Private methods: `_leading_underscore`

### Commit Messages

```
feat: add columnar storage support for analytics tables
fix: resolve cache invalidation race condition in WriteFanOut
docs: update Docker guide with Citus worker scaling
refactor: extract common pagination logic to DataRenderer
test: add integration tests for identity resolution
```

Format: `type: description`

Types: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`, `perf`

---

## Areas for Contribution

### High Priority

- [ ] Test coverage for all engines
- [ ] Benchmarking suite
- [ ] SDK clients (Python, TypeScript, Go, Rust)
- [ ] Helm chart for Kubernetes
- [ ] CI/CD pipeline (GitHub Actions)

### Medium Priority

- [ ] CortexQL ANTLR4 grammar (replace regex parser)
- [ ] XGBoost churn prediction model
- [ ] pgvector integration as VectorCore alternative
- [ ] PgBouncer connection pool integration
- [ ] Read replica auto-discovery

### Good First Issues

- [ ] Add more SQL injection patterns to Amygdala
- [ ] Add CSV export format to DataRenderer
- [ ] Add more RFM segment rules
- [ ] Improve error messages in CortexQL parser
- [ ] Add request/response logging middleware

---

## Pull Request Process

1. Fork the repository
2. Create a feature branch (`feat/my-feature`)
3. Make your changes
4. Add tests for new functionality
5. Ensure all tests pass
6. Update documentation if needed
7. Submit a pull request

### PR Template

```markdown
## Summary
Brief description of changes.

## Changes
- Added X
- Fixed Y
- Updated Z

## Testing
- [ ] Unit tests added/updated
- [ ] Integration tests pass
- [ ] Manual testing performed

## Documentation
- [ ] Docs updated (if applicable)
- [ ] API changes documented
```

---

## License

By contributing to CortexDB, you agree that your contributions will be licensed under the same license as the project.

CortexDB™ is proprietary software of Nirlab Inc. Contributor License Agreement (CLA) required for external contributions.

---

*Thank you for making CortexDB better.*

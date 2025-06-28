# Discovery Cluster – AI Trading Signal Platform

This repository hosts the **Discovery Cluster** of a dual-cluster AI trading platform designed for Indian equity markets. The Discovery Cluster is responsible for real-time signal generation, explainability, and cross-cluster communication.

## Tech-stack (MVP / Docker-Compose)

* FastAPI / Python 3.12 – API gateway & authentication
* Google **ADK** + LiteLLM – multi-agent signal generation
* PostgreSQL 16 + TimescaleDB – time-series storage
* Apache Pulsar – event streaming
* Redis – caching & session store
* Qdrant – vector database (semantic memory)
* Elasticsearch – news search index
* Prometheus + Grafana + Jaeger – monitoring / tracing
* React 18 + TypeScript – trader dashboard

## Local Development

### Prerequisites
- **Docker & Docker Compose**
- **Make** (Linux/macOS) or use manual commands (Windows)
- **jq** (for health-check script): `brew install jq` or `choco install jq`
- **Python 3.12+** (for FastAPI services)

### Quick Start

#### With Make (Linux/macOS/WSL):
```bash
# Complete setup and start all services
make dev-start

# View all available commands
make help

# Stop services when done
make dev-stop
```

#### PowerShell Script (Windows):
```powershell
# Complete setup and start all services
.\scripts\dev-commands.ps1 dev-start

# View all available commands
.\scripts\dev-commands.ps1 help

# Stop services when done
.\scripts\dev-commands.ps1 dev-stop
```

#### Manual Commands (Any Platform):
```bash
# 1. Setup environment
cp .env.example .env
# Edit .env with your actual values

# 2. Start all infrastructure services
docker-compose up -d

# 3. Check service health
docker-compose ps

# 4. View logs
docker-compose logs -f

# 5. Stop services
docker-compose down
```

### Development Workflow
```bash
# 1. Clone & create Python environment
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt  # (will be generated later)

# 2. Start infrastructure
make up   # or docker-compose up -d

# 3. Run FastAPI backend (auto-reload)
uvicorn app.main:app --reload

# 4. Start React frontend
cd frontend && npm install && npm start
```

### Service Access Points
| Service | URL | Credentials |
|---------|-----|-------------|
| **Grafana Dashboard** | http://localhost:3000 | admin / admin123 |
| **Prometheus** | http://localhost:9090 | - |
| **Jaeger Tracing** | http://localhost:16686 | - |
| **MinIO Console** | http://localhost:9001 | minioadmin / minioadmin123 |
| **Elasticsearch** | http://localhost:9200 | - |

## Makefile Commands
| Command | Description |
|---------|-------------|
| `make help` | Show all available commands |
| `make dev-start` | Complete development setup |
| `make dev-stop` | Stop development environment |
| `make up` / `make down` | Start/stop all services |
| `make logs` | Follow all service logs |
| `make status` | Show service status |
| `make health` | Check service health |
| `make db-shell` | Open PostgreSQL shell |
| `make redis-cli` | Open Redis CLI |
| `make clean` | Clean up containers and volumes |
| `make ports` | Show all exposed ports |
| `make quick-check` | Quick health check |

## Taskmaster Workflow
All development follows **test-driven development**. See `.taskmaster/tasks/tasks.json` for the project plan.

---
© 2025 Verities Research 
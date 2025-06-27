# Discovery Cluster - Development Makefile
# Trading Signal Generation Platform
.PHONY: help build up down logs status clean test shell lint format check-env setup-env backup restore

# Default target
help: ## Show this help message
	@echo "Discovery Cluster - Development Commands"
	@echo "========================================"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

# Environment Setup
setup-env: ## Create .env file from template
	@if [ ! -f .env ]; then \
		cp .env.example .env; \
		echo "✅ Created .env file from template"; \
		echo "⚠️  Please update .env with your actual values"; \
	else \
		echo "📝 .env file already exists"; \
	fi

check-env: ## Check if required environment variables are set
	@echo "🔍 Checking environment variables..."
	@if [ ! -f .env ]; then \
		echo "❌ .env file not found. Run 'make setup-env' first"; \
		exit 1; \
	fi
	@echo "✅ .env file exists"

# Docker Compose Operations
build: check-env ## Build all Docker containers
	@echo "🔨 Building Docker containers..."
	docker-compose build --no-cache

up: check-env ## Start all services in detached mode
	@echo "🚀 Starting Discovery Cluster services..."
	docker-compose up -d

up-logs: check-env ## Start all services with logs
	@echo "🚀 Starting Discovery Cluster services with logs..."
	docker-compose up

down: ## Stop and remove all containers
	@echo "🛑 Stopping Discovery Cluster services..."
	docker-compose down

down-volumes: ## Stop and remove all containers and volumes
	@echo "🗑️  Stopping services and removing volumes..."
	docker-compose down -v

restart: down up ## Restart all services
	@echo "🔄 Restarting Discovery Cluster..."

# Logs and Monitoring
logs: ## Show logs for all services
	docker-compose logs -f

logs-service: ## Show logs for specific service (make logs-service SERVICE=postgres)
	@if [ -z "$(SERVICE)" ]; then \
		echo "Usage: make logs-service SERVICE=<service_name>"; \
		echo "Available services: postgres, redis, pulsar, qdrant, elasticsearch, minio, prometheus, grafana, jaeger"; \
	else \
		docker-compose logs -f $(SERVICE); \
	fi

status: ## Show status of all services
	@echo "📊 Service Status:"
	@docker-compose ps

health: ## Check health of all services
	@echo "🏥 Health Check:"
	@docker-compose ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}"

# Service Management
shell: ## Open shell in specific service (make shell SERVICE=postgres)
	@if [ -z "$(SERVICE)" ]; then \
		echo "Usage: make shell SERVICE=<service_name>"; \
		echo "Available services: postgres, redis, pulsar, qdrant, elasticsearch, minio, prometheus, grafana, jaeger"; \
	else \
		docker-compose exec $(SERVICE) sh; \
	fi

# Database Operations
db-shell: ## Open PostgreSQL shell
	docker-compose exec postgres psql -U discovery_user -d discovery_cluster

db-backup: ## Backup PostgreSQL database
	@echo "💾 Creating database backup..."
	@mkdir -p backups
	docker-compose exec postgres pg_dump -U discovery_user discovery_cluster > backups/discovery_cluster_$(shell date +%Y%m%d_%H%M%S).sql
	@echo "✅ Database backup created in backups/"

db-restore: ## Restore PostgreSQL database from backup (make db-restore FILE=backup.sql)
	@if [ -z "$(FILE)" ]; then \
		echo "Usage: make db-restore FILE=backup.sql"; \
		echo "Available backups:"; \
		ls -la backups/*.sql 2>/dev/null || echo "No backups found"; \
	else \
		docker-compose exec -T postgres psql -U discovery_user -d discovery_cluster < $(FILE); \
		echo "✅ Database restored from $(FILE)"; \
	fi

# Redis Operations
redis-cli: ## Open Redis CLI
	docker-compose exec redis redis-cli

redis-flush: ## Flush all Redis data (WARNING: destructive)
	@echo "⚠️  This will delete all Redis data. Continue? [y/N]" && read ans && [ $${ans:-N} = y ]
	docker-compose exec redis redis-cli FLUSHALL
	@echo "🗑️  Redis data flushed"

# MinIO Operations
minio-console: ## Open MinIO browser console
	@echo "🌐 MinIO Console: http://localhost:9001"
	@echo "   Username: minioadmin"
	@echo "   Password: minioadmin123"

# Monitoring Access
grafana: ## Open Grafana dashboard
	@echo "📊 Grafana Dashboard: http://localhost:3000"
	@echo "   Username: admin"
	@echo "   Password: admin123"

prometheus: ## Open Prometheus web UI
	@echo "📈 Prometheus: http://localhost:9090"

jaeger: ## Open Jaeger tracing UI
	@echo "🔍 Jaeger Tracing: http://localhost:16686"

elasticsearch: ## Check Elasticsearch cluster health
	@echo "🔍 Elasticsearch cluster health:"
	curl -s http://localhost:9200/_cluster/health | jq .

# Development Tools
lint: ## Run code linting (when Python code is added)
	@echo "🧹 Running linting..."
	@echo "⚠️  Linting tools will be added when Python services are implemented"

format: ## Format code (when Python code is added)
	@echo "✨ Formatting code..."
	@echo "⚠️  Code formatting tools will be added when Python services are implemented"

test: ## Run tests (when tests are added)
	@echo "🧪 Running tests..."
	@echo "⚠️  Test suite will be added when services are implemented"

# Cleanup and Maintenance
clean: down ## Clean up containers, networks, and orphaned volumes
	@echo "🧹 Cleaning up..."
	docker-compose down --remove-orphans
	docker system prune -f
	docker volume prune -f

clean-all: ## Remove everything including volumes and images
	@echo "⚠️  This will remove all containers, volumes, networks, and images. Continue? [y/N]" && read ans && [ $${ans:-N} = y ]
	docker-compose down -v --remove-orphans
	docker system prune -af
	docker volume prune -f

# Development Workflow
dev-start: setup-env up health ## Complete development setup
	@echo ""
	@echo "🎉 Discovery Cluster is ready for development!"
	@echo ""
	@echo "📊 Access Points:"
	@echo "   - Grafana Dashboard: http://localhost:3000 (admin/admin123)"
	@echo "   - Prometheus: http://localhost:9090"
	@echo "   - Jaeger Tracing: http://localhost:16686"
	@echo "   - MinIO Console: http://localhost:9001 (minioadmin/minioadmin123)"
	@echo "   - Elasticsearch: http://localhost:9200"
	@echo ""
	@echo "🔧 Quick Commands:"
	@echo "   - View logs: make logs"
	@echo "   - Check status: make status"
	@echo "   - Database shell: make db-shell"
	@echo "   - Redis CLI: make redis-cli"
	@echo ""

dev-stop: down ## Stop development environment
	@echo "🛑 Development environment stopped"

# Quick Access Commands
quick-check: ## Quick health check of all services
	@echo "🔍 Quick Health Check:"
	@echo "PostgreSQL:" && docker-compose exec postgres pg_isready -U discovery_user || echo "❌ PostgreSQL not ready"
	@echo "Redis:" && docker-compose exec redis redis-cli ping || echo "❌ Redis not ready"
	@echo "Elasticsearch:" && curl -s http://localhost:9200/_cluster/health | jq -r '.status' || echo "❌ Elasticsearch not ready"
	@echo "MinIO:" && curl -s http://localhost:9000/minio/health/live || echo "❌ MinIO not ready"
	@echo "Prometheus:" && curl -s http://localhost:9090/-/healthy || echo "❌ Prometheus not ready"
	@echo "Grafana:" && curl -s http://localhost:3000/api/health | jq -r '.database' || echo "❌ Grafana not ready"

# Port Information
ports: ## Show all exposed ports
	@echo "🌐 Exposed Ports:"
	@echo "   5432  - PostgreSQL"
	@echo "   6379  - Redis"
	@echo "   6650  - Pulsar (protocol)"
	@echo "   8080  - Pulsar (admin)"
	@echo "   6333  - Qdrant (HTTP)"
	@echo "   6334  - Qdrant (gRPC)"
	@echo "   9200  - Elasticsearch (HTTP)"
	@echo "   9300  - Elasticsearch (transport)"
	@echo "   9000  - MinIO (API)"
	@echo "   9001  - MinIO (Console)"
	@echo "   9090  - Prometheus"
	@echo "   3000  - Grafana"
	@echo "   16686 - Jaeger (UI)"
	@echo "   4317  - Jaeger (OTLP gRPC)"
	@echo "   4318  - Jaeger (OTLP HTTP)"

# Documentation
docs: ## Show documentation links
	@echo "📚 Documentation:"
	@echo "   - PostgreSQL: https://www.postgresql.org/docs/"
	@echo "   - Redis: https://redis.io/docs/"
	@echo "   - Apache Pulsar: https://pulsar.apache.org/docs/"
	@echo "   - Qdrant: https://qdrant.tech/documentation/"
	@echo "   - Elasticsearch: https://www.elastic.co/guide/"
	@echo "   - MinIO: https://min.io/docs/"
	@echo "   - Prometheus: https://prometheus.io/docs/"
	@echo "   - Grafana: https://grafana.com/docs/"
	@echo "   - Jaeger: https://www.jaegertracing.io/docs/"
	@echo ""
	@echo "📖 Project Documentation:"
	@echo "   - README.md: Project overview and setup"
	@echo "   - .env.example: Environment configuration template"
	@echo "   - docker-compose.yml: Service definitions" 
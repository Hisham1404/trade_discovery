#!/bin/bash

# Production Trading Platform Startup Script
# This script starts the complete Docker Compose infrastructure

set -e

echo "🚀 Starting Production Trading Platform Infrastructure"
echo "=================================================="

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo "❌ Error: Docker is not running. Please start Docker first."
    exit 1
fi

# Check if Docker Compose is available
if ! command -v docker-compose &> /dev/null; then
    echo "❌ Error: docker-compose is not installed. Please install it first."
    exit 1
fi

# Create necessary directories
echo "📁 Creating configuration directories..."
mkdir -p config/prometheus/rules
mkdir -p config/grafana/provisioning/datasources
mkdir -p config/grafana/provisioning/dashboards
mkdir -p config/grafana/dashboards
mkdir -p config/logstash/pipeline
mkdir -p config/postgres
mkdir -p config/redis
mkdir -p config/pulsar
mkdir -p config/nginx/ssl
mkdir -p logs

# Check if .env file exists
if [ ! -f .env.production ]; then
    echo "❌ Error: .env.production file not found!"
    echo "Please copy .env.production.example to .env.production and configure it."
    exit 1
fi

# Validate required environment variables
echo "🔍 Validating environment variables..."
source .env.production

required_vars=(
    "POSTGRES_PASSWORD"
    "REDIS_PASSWORD" 
    "GRAFANA_PASSWORD"
)

for var in "${required_vars[@]}"; do
    if [ -z "${!var}" ]; then
        echo "❌ Error: Required environment variable $var is not set in .env.production"
        exit 1
    fi
done

echo "✅ Environment variables validated"

# Pull latest images
echo "📦 Pulling latest Docker images..."
docker-compose -f docker-compose.production.yml pull

# Start infrastructure services first
echo "🏗️ Starting infrastructure services..."
docker-compose -f docker-compose.production.yml up -d \
    postgres-primary \
    redis \
    pulsar \
    elasticsearch

# Wait for infrastructure to be ready
echo "⏳ Waiting for infrastructure services to be ready..."
echo "   - PostgreSQL..."
until docker-compose -f docker-compose.production.yml exec -T postgres-primary pg_isready -U trading_user > /dev/null 2>&1; do
    sleep 2
done

echo "   - Redis..."
until docker-compose -f docker-compose.production.yml exec -T redis redis-cli ping > /dev/null 2>&1; do
    sleep 2
done

echo "   - Pulsar..."
until curl -f http://localhost:8080/admin/v2/clusters > /dev/null 2>&1; do
    sleep 5
done

echo "   - Elasticsearch..."
until curl -f http://localhost:9200/_cluster/health > /dev/null 2>&1; do
    sleep 5
done

echo "✅ Infrastructure services are ready"

# Start monitoring services
echo "📊 Starting monitoring services..."
docker-compose -f docker-compose.production.yml up -d \
    prometheus \
    grafana \
    node-exporter \
    cadvisor \
    logstash \
    kibana

# Wait for monitoring to be ready
echo "⏳ Waiting for monitoring services..."
sleep 10

# Start application services
echo "🔧 Starting application services..."
docker-compose -f docker-compose.production.yml up -d \
    discovery-cluster \
    execution-cluster \
    risk-cluster

# Wait for applications to be ready
echo "⏳ Waiting for application services..."
sleep 15

# Start load balancer
echo "⚖️ Starting load balancer..."
docker-compose -f docker-compose.production.yml up -d nginx

# Final health checks
echo "🏥 Performing health checks..."

services=(
    "http://localhost:8000/health:Discovery Cluster"
    "http://localhost:8002/health:Execution Cluster" 
    "http://localhost:8004/health:Risk Cluster"
    "http://localhost:9090:Prometheus"
    "http://localhost:3000:Grafana"
    "http://localhost:5601:Kibana"
    "http://localhost:80/health:Load Balancer"
)

for service in "${services[@]}"; do
    url="${service%%:*}"
    name="${service##*:}"
    
    if curl -f "$url" > /dev/null 2>&1; then
        echo "   ✅ $name is healthy"
    else
        echo "   ⚠️ $name is not responding (may need more time)"
    fi
done

echo ""
echo "🎉 Trading Platform Infrastructure Started Successfully!"
echo "=================================================="
echo ""
echo "📋 Service URLs:"
echo "   🔗 API Gateway:        http://localhost"
echo "   📊 Grafana Dashboard:  http://localhost:3000 (admin/${GRAFANA_PASSWORD})"
echo "   📈 Prometheus:         http://localhost:9090"
echo "   📋 Kibana Logs:        http://localhost:5601"
echo "   🔍 Discovery API:      http://localhost:8000"
echo "   ⚡ Execution API:      http://localhost:8002"
echo "   🛡️ Risk API:          http://localhost:8004"
echo ""
echo "📊 Monitoring:"
echo "   💾 PostgreSQL:        localhost:5432"
echo "   🗄️ Redis:             localhost:6379"
echo "   📨 Pulsar Admin:       http://localhost:8080"
echo "   🔍 Elasticsearch:     http://localhost:9200"
echo ""
echo "🚀 Ready to start trading!"
echo ""
echo "To stop all services: ./scripts/stop-production.sh"
echo "To view logs: docker-compose -f docker-compose.production.yml logs -f [service-name]"
echo "To restart: docker-compose -f docker-compose.production.yml restart [service-name]" 
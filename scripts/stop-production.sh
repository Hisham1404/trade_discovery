#!/bin/bash

# Production Trading Platform Stop Script
# This script safely stops all Docker Compose services

set -e

echo "🛑 Stopping Production Trading Platform Infrastructure"
echo "===================================================="

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo "❌ Error: Docker is not running."
    exit 1
fi

# Check if docker-compose file exists
if [ ! -f docker-compose.production.yml ]; then
    echo "❌ Error: docker-compose.production.yml not found!"
    exit 1
fi

echo "🔄 Gracefully stopping all services..."

# Stop services in reverse order of startup
echo "   🛑 Stopping load balancer..."
docker-compose -f docker-compose.production.yml stop nginx

echo "   🛑 Stopping application services..."
docker-compose -f docker-compose.production.yml stop \
    discovery-cluster \
    execution-cluster \
    risk-cluster

echo "   🛑 Stopping monitoring services..."
docker-compose -f docker-compose.production.yml stop \
    prometheus \
    grafana \
    node-exporter \
    cadvisor \
    logstash \
    kibana

echo "   🛑 Stopping infrastructure services..."
docker-compose -f docker-compose.production.yml stop \
    postgres-primary \
    redis \
    pulsar \
    elasticsearch

echo "✅ All services stopped successfully"

# Optional: Ask if user wants to remove containers and volumes
echo ""
read -p "Do you want to remove containers and volumes? (y/N): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "🗑️ Removing containers and volumes..."
    docker-compose -f docker-compose.production.yml down -v
    echo "✅ Containers and volumes removed"
else
    echo "📦 Containers and volumes preserved (use 'docker-compose -f docker-compose.production.yml down -v' to remove them later)"
fi

echo ""
echo "🏁 Trading Platform Infrastructure Stopped"
echo "To start again: ./scripts/start-production.sh" 
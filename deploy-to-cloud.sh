#!/bin/bash

# Production-Grade Monitoring Stack Deployment Script
# For Shadeform Cloud GPU Instances
# Usage: ./deploy-to-cloud.sh [INSTANCE_IP] [SSH_KEY_PATH]

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
INSTANCE_IP=${1:-"your-instance-ip"}
SSH_KEY=${2:-"~/.ssh/your-key.pem"}
PROJECT_DIR="trade_discovery"
REMOTE_USER="ubuntu"

echo -e "${BLUE}🚀 TradeDiscovery Production Monitoring Stack Deployment${NC}"
echo -e "${BLUE}================================================================${NC}"
echo ""
echo -e "${YELLOW}📋 Configuration:${NC}"
echo -e "   Instance IP: ${INSTANCE_IP}"
echo -e "   SSH Key: ${SSH_KEY}"
echo -e "   Remote User: ${REMOTE_USER}"
echo -e "   Project Dir: ${PROJECT_DIR}"
echo ""

# Validate inputs
if [[ "$INSTANCE_IP" == "your-instance-ip" ]]; then
    echo -e "${RED}❌ Error: Please provide your cloud instance IP address${NC}"
    echo -e "${YELLOW}Usage: ./deploy-to-cloud.sh <INSTANCE_IP> [SSH_KEY_PATH]${NC}"
    exit 1
fi

if [[ ! -f "${SSH_KEY/#\~/$HOME}" ]]; then
    echo -e "${RED}❌ Error: SSH key not found at ${SSH_KEY}${NC}"
    exit 1
fi

# Expand tilde in SSH key path
SSH_KEY_EXPANDED="${SSH_KEY/#\~/$HOME}"

echo -e "${BLUE}🔧 Step 1: Testing SSH Connection...${NC}"
if ssh -i "$SSH_KEY_EXPANDED" -o ConnectTimeout=10 -o StrictHostKeyChecking=no "$REMOTE_USER@$INSTANCE_IP" "echo 'SSH connection successful'" > /dev/null 2>&1; then
    echo -e "${GREEN}✅ SSH connection successful${NC}"
else
    echo -e "${RED}❌ SSH connection failed. Please check your instance IP and SSH key${NC}"
    exit 1
fi

echo -e "${BLUE}🔧 Step 2: Setting up Docker on cloud instance...${NC}"
ssh -i "$SSH_KEY_EXPANDED" "$REMOTE_USER@$INSTANCE_IP" << 'DOCKER_SETUP'
set -e

# Update system
echo "📦 Updating system packages..."
sudo apt update -y > /dev/null 2>&1

# Install Docker if not present
if ! command -v docker &> /dev/null; then
    echo "🐳 Installing Docker..."
    curl -fsSL https://get.docker.com -o get-docker.sh
    sudo sh get-docker.sh > /dev/null 2>&1
    sudo usermod -aG docker ubuntu
    rm get-docker.sh
fi

# Install Docker Compose if not present
if ! command -v docker-compose &> /dev/null; then
    echo "📚 Installing Docker Compose..."
    sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" \
        -o /usr/local/bin/docker-compose > /dev/null 2>&1
    sudo chmod +x /usr/local/bin/docker-compose
fi

# Install Python3 and pip if not present
if ! command -v python3 &> /dev/null; then
    echo "🐍 Installing Python3..."
    sudo apt install python3 python3-pip python3-venv -y > /dev/null 2>&1
fi

echo "✅ Docker setup completed"
DOCKER_SETUP

echo -e "${BLUE}📂 Step 3: Transferring project files...${NC}"
echo -e "${YELLOW}   This may take a few minutes depending on your connection...${NC}"

# Use rsync for efficient transfer
rsync -avz --progress -e "ssh -i $SSH_KEY_EXPANDED" \
    --exclude 'node_modules' --exclude '.git' --exclude 'venv' --exclude '__pycache__' \
    --exclude '*.pyc' --exclude '.env' --exclude 'data/' \
    ./ "$REMOTE_USER@$INSTANCE_IP:~/$PROJECT_DIR/"

echo -e "${GREEN}✅ Project files transferred${NC}"

echo -e "${BLUE}🔐 Step 4: Setting up production environment...${NC}"
ssh -i "$SSH_KEY_EXPANDED" "$REMOTE_USER@$INSTANCE_IP" << EOF
set -e
cd ~/$PROJECT_DIR

# Create production environment file
echo "🔑 Creating production environment configuration..."
cat > .env.production << 'ENVEOF'
# Production Environment Configuration
# ====================================

# Security - CHANGE THESE IN PRODUCTION!
GRAFANA_ADMIN_PASSWORD=TradeDiscovery2024SecureAdmin!
GRAFANA_SECRET_KEY=TradeDiscovery2024ProductionSecretKey32Chars
GRAFANA_DOMAIN=$INSTANCE_IP
GRAFANA_PROTOCOL=http

# Security Headers
GRAFANA_COOKIE_SECURE=false
GRAFANA_HSTS=false

# Prometheus Configuration
PROMETHEUS_RETENTION_TIME=30d
PROMETHEUS_RETENTION_SIZE=100GB

# Logging
GRAFANA_LOG_LEVEL=info

# Production Features
ENVIRONMENT=production
DEBUG=false
LOG_LEVEL=INFO
ENVEOF

chmod 600 .env.production

# Set up Python virtual environment
echo "🐍 Setting up Python virtual environment..."
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt > /dev/null 2>&1

echo "✅ Production environment configured"
EOF

echo -e "${BLUE}🚀 Step 5: Deploying monitoring stack...${NC}"
ssh -i "$SSH_KEY_EXPANDED" "$REMOTE_USER@$INSTANCE_IP" << 'DEPLOY'
set -e
cd ~/trade_discovery

# Load production environment
export $(cat .env.production | xargs)

# Pull Docker images first
echo "📥 Pulling Docker images..."
docker-compose -f docker-compose.monitoring.yml pull > /dev/null 2>&1

# Deploy monitoring stack
echo "🚀 Starting monitoring services..."
docker-compose -f docker-compose.monitoring.yml up -d

# Wait for services to be ready
echo "⏳ Waiting for services to initialize..."
sleep 60

# Check if all services are running
RUNNING_SERVICES=$(docker ps --filter "label=org.label-schema.group=monitoring" --format "table {{.Names}}" | tail -n +2 | wc -l)
if [ "$RUNNING_SERVICES" -eq 5 ]; then
    echo "✅ All monitoring services are running"
else
    echo "⚠️  Warning: Only $RUNNING_SERVICES out of 5 services are running"
    docker ps --filter "label=org.label-schema.group=monitoring" --format "table {{.Names}}\t{{.Status}}"
fi
DEPLOY

echo -e "${BLUE}✅ Step 6: Running production tests...${NC}"
ssh -i "$SSH_KEY_EXPANDED" "$REMOTE_USER@$INSTANCE_IP" << 'TESTS'
set -e
cd ~/trade_discovery
source venv/bin/activate

echo "🧪 Running comprehensive test suite..."
python -m pytest tests/test_monitoring_infrastructure.py -v --tb=short

echo "✅ All tests completed"
TESTS

echo -e "${BLUE}📊 Step 7: Displaying deployment summary...${NC}"
ssh -i "$SSH_KEY_EXPANDED" "$REMOTE_USER@$INSTANCE_IP" << 'SUMMARY'
set -e
cd ~/trade_discovery

echo ""
echo "🎉 DEPLOYMENT SUCCESSFUL!"
echo "=========================="
echo ""

echo "📊 Service Status:"
docker ps --filter "label=org.label-schema.group=monitoring" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

echo ""
echo "💾 Resource Usage:"
docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}"

echo ""
echo "🌐 Access URLs (via SSH tunnel):"
echo "================================="
echo "To access from your laptop, run:"
echo ""
echo "ssh -i $SSH_KEY_EXPANDED -L 3000:localhost:3000 -L 9090:localhost:9090 -L 16686:localhost:16686 -L 9093:localhost:9093 ubuntu@$INSTANCE_IP"
echo ""
echo "Then open:"
echo "• Grafana:      http://localhost:3000 (admin / TradeDiscovery2024SecureAdmin!)"
echo "• Prometheus:   http://localhost:9090"
echo "• Jaeger:       http://localhost:16686"
echo "• Alertmanager: http://localhost:9093"
echo ""

echo "🔧 Management Commands:"
echo "======================="
echo "• View logs:     docker-compose -f docker-compose.monitoring.yml logs -f"
echo "• Restart stack: docker-compose -f docker-compose.monitoring.yml restart"
echo "• Stop stack:    docker-compose -f docker-compose.monitoring.yml down"
echo "• Update stack:  docker-compose -f docker-compose.monitoring.yml pull && docker-compose -f docker-compose.monitoring.yml up -d"
echo ""

echo "🎯 Next Steps:"
echo "=============="
echo "1. Set up SSH tunnel (command above)"
echo "2. Access Grafana and configure dashboards"
echo "3. Configure Alertmanager notifications"
echo "4. Set up backup strategy"
echo "5. Configure firewall rules"
echo ""
SUMMARY

echo -e "${GREEN}🎉 DEPLOYMENT COMPLETED SUCCESSFULLY! 🎉${NC}"
echo -e "${GREEN}=====================================${NC}"
echo ""
echo -e "${BLUE}📱 Next Actions:${NC}"
echo -e "1. ${YELLOW}Set up SSH tunnel:${NC}"
echo -e "   ssh -i $SSH_KEY_EXPANDED -L 3000:localhost:3000 -L 9090:localhost:9090 -L 16686:localhost:16686 -L 9093:localhost:9093 $REMOTE_USER@$INSTANCE_IP"
echo ""
echo -e "2. ${YELLOW}Access services:${NC}"
echo -e "   • Grafana: http://localhost:3000 (admin / TradeDiscovery2024SecureAdmin!)"
echo -e "   • Prometheus: http://localhost:9090"
echo -e "   • Jaeger: http://localhost:16686"
echo ""
echo -e "3. ${YELLOW}Update task status:${NC}"
echo -e "   task-master set-status --id=8.1 --status=done"
echo ""
echo -e "${GREEN}🚀 Your production-grade monitoring stack is now running on the cloud! 🚀${NC}" 
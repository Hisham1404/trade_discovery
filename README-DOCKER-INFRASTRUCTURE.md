# 🐳 Docker Compose Infrastructure Setup

## 🏗️ **Production-Grade Trading Platform Infrastructure**

This Docker Compose setup provides a complete, production-ready infrastructure for the cross-cluster trading platform with **enterprise-grade monitoring, logging, and resilience**.

## 📋 **Infrastructure Components**

### **Core Services**
- 🗄️ **PostgreSQL + TimescaleDB** - Primary database with time-series capabilities
- 🗄️ **Redis** - High-performance caching layer
- 📨 **Apache Pulsar** - Message broker for cross-cluster communication
- ⚖️ **NGINX** - Load balancer and reverse proxy

### **Application Clusters**  
- 🔍 **Discovery Cluster** - Signal discovery and analysis
- ⚡ **Execution Cluster** - Order execution and management
- 🛡️ **Risk Cluster** - Risk management and monitoring

### **Monitoring Stack**
- 📊 **Prometheus** - Metrics collection and storage
- 📈 **Grafana** - Dashboards and visualization
- 📉 **Node Exporter** - System metrics
- 📦 **cAdvisor** - Container metrics

### **Logging Stack**
- 🔍 **Elasticsearch** - Log storage and search
- 📝 **Logstash** - Log processing pipeline
- 📋 **Kibana** - Log visualization and analysis

## 🚀 **Quick Start**

### **Prerequisites**
```bash
# Required software
- Docker 20.10+
- Docker Compose 2.0+
- 8GB+ RAM available
- 50GB+ free disk space
```

### **1. Clone and Setup**
```bash
git clone <repository-url>
cd trade_discovery

# Copy environment template
cp .env.production.example .env.production

# Configure your passwords and API keys
nano .env.production
```

### **2. Configure Environment**
Edit `.env.production` with your settings:
```bash
# Database passwords
POSTGRES_PASSWORD=your_secure_postgres_password
REDIS_PASSWORD=your_secure_redis_password

# Monitoring
GRAFANA_PASSWORD=your_secure_grafana_password

# API keys
JWT_SECRET=your_jwt_secret_key
BROKER_API_KEY=your_broker_api_key
```

### **3. Start Infrastructure**
```bash
# Make scripts executable
chmod +x scripts/*.sh

# Start all services
./scripts/start-production.sh
```

### **4. Verify Deployment**
```bash
# Check service health
docker-compose -f docker-compose.production.yml ps

# View logs
docker-compose -f docker-compose.production.yml logs -f discovery-cluster
```

## 📊 **Service Endpoints**

### **API Gateways**
- 🔗 **Main API Gateway**: `http://localhost`
- 🔍 **Discovery API**: `http://localhost:8000`
- ⚡ **Execution API**: `http://localhost:8002`  
- 🛡️ **Risk API**: `http://localhost:8004`

### **Monitoring Dashboards**
- 📊 **Grafana**: `http://localhost:3000` (admin/your_password)
- 📈 **Prometheus**: `http://localhost:9090`
- 📋 **Kibana**: `http://localhost:5601`

### **Database Access**
- 💾 **PostgreSQL**: `localhost:5432` (trading_user/your_password)
- 🗄️ **Redis**: `localhost:6379`
- 📨 **Pulsar Admin**: `http://localhost:8080`
- 🔍 **Elasticsearch**: `http://localhost:9200`

## 🔧 **Configuration**

### **Environment Variables**
| Variable | Description | Required |
|----------|-------------|----------|
| `POSTGRES_PASSWORD` | PostgreSQL database password | ✅ |
| `REDIS_PASSWORD` | Redis cache password | ✅ |
| `GRAFANA_PASSWORD` | Grafana admin password | ✅ |
| `LOG_LEVEL` | Application log level (INFO/DEBUG) | ✅ |
| `ENABLE_METRICS` | Enable Prometheus metrics | ❌ |
| `RATE_LIMIT_PER_MINUTE` | API rate limiting | ❌ |
| `CB_FAILURE_THRESHOLD` | Circuit breaker threshold | ❌ |

### **Resource Limits**
```yaml
# Default per-service limits
PostgreSQL: 2 CPU, 4GB RAM
Redis: 1 CPU, 2GB RAM  
Pulsar: 2 CPU, 4GB RAM
Applications: 2 CPU, 3GB RAM each
Monitoring: 1 CPU, 2GB RAM total
```

### **Port Mappings**
```yaml
# Application Services
8000: Discovery Cluster API
8002: Execution Cluster API
8004: Risk Cluster API

# Infrastructure
5432: PostgreSQL
6379: Redis
6650: Pulsar
9200: Elasticsearch

# Monitoring
3000: Grafana
9090: Prometheus
5601: Kibana
```

## 🛠️ **Operations**

### **Starting Services**
```bash
# Start all services
./scripts/start-production.sh

# Start specific service
docker-compose -f docker-compose.production.yml up -d discovery-cluster

# Start with rebuild
docker-compose -f docker-compose.production.yml up -d --build
```

### **Stopping Services**
```bash
# Graceful stop all
./scripts/stop-production.sh

# Stop specific service  
docker-compose -f docker-compose.production.yml stop risk-cluster

# Stop and remove everything
docker-compose -f docker-compose.production.yml down -v
```

### **Monitoring & Logs**
```bash
# View live logs
docker-compose -f docker-compose.production.yml logs -f

# View specific service logs
docker-compose -f docker-compose.production.yml logs -f discovery-cluster

# Check service health
docker-compose -f docker-compose.production.yml ps

# View resource usage
docker stats
```

### **Scaling Services**
```bash
# Scale application services
docker-compose -f docker-compose.production.yml up -d --scale discovery-cluster=2

# Scale execution cluster
docker-compose -f docker-compose.production.yml up -d --scale execution-cluster=3
```

## 🔍 **Troubleshooting**

### **Common Issues**

#### **Services Won't Start**
```bash
# Check Docker daemon
docker info

# Check compose file syntax
docker-compose -f docker-compose.production.yml config

# Check environment variables
source .env.production && env | grep -E "(POSTGRES|REDIS|GRAFANA)"
```

#### **Database Connection Issues**
```bash
# Test PostgreSQL connection
docker-compose -f docker-compose.production.yml exec postgres-primary \
  psql -U trading_user -d trading -c "SELECT 1;"

# Check Redis connection  
docker-compose -f docker-compose.production.yml exec redis \
  redis-cli ping
```

#### **Application Startup Issues**
```bash
# Check application logs
docker-compose -f docker-compose.production.yml logs discovery-cluster

# Restart specific service
docker-compose -f docker-compose.production.yml restart discovery-cluster

# Check health endpoints
curl http://localhost:8000/health
```

#### **Memory Issues**
```bash
# Check Docker memory usage
docker system df

# Clean up unused resources
docker system prune -a

# Increase Docker memory limit (Docker Desktop)
# Settings > Resources > Memory > 8GB+
```

### **Performance Tuning**

#### **Database Optimization**
```bash
# PostgreSQL performance settings in config/postgres/postgresql.conf
shared_buffers = 2GB
effective_cache_size = 6GB
work_mem = 256MB
maintenance_work_mem = 1GB
```

#### **Redis Optimization**
```bash
# Redis settings in config/redis/redis.conf
maxmemory 2gb
maxmemory-policy allkeys-lru
save 900 1
```

#### **Application Tuning**
```bash
# Environment variables for performance
MAX_CONCURRENT_EVENTS=200
EVENT_BATCH_SIZE=20
DB_POOL_SIZE=30
```

## 🔒 **Security Considerations**

### **Production Hardening**
```bash
# 1. Change default passwords
POSTGRES_PASSWORD=<strong-random-password>
REDIS_PASSWORD=<strong-random-password>  
GRAFANA_PASSWORD=<strong-random-password>

# 2. Enable SSL/TLS (add certificates to config/nginx/ssl/)
# 3. Configure firewall rules
# 4. Enable authentication for all services
# 5. Regular security updates
```

### **Network Security**
```bash
# Docker network isolation
networks:
  trade_network:
    driver: bridge
    internal: true  # Disable external access
```

## 📈 **Monitoring & Alerts**

### **Grafana Dashboards**
- 📊 **Trading Platform Overview** - Key metrics and health
- 📈 **Application Performance** - Response times and throughput  
- 🗄️ **Infrastructure Metrics** - CPU, memory, disk usage
- 📨 **Message Broker Stats** - Pulsar topic and consumer metrics
- 💾 **Database Performance** - PostgreSQL and Redis metrics

### **Prometheus Metrics**
```bash
# Application metrics endpoint
curl http://localhost:8000/metrics

# Infrastructure metrics
curl http://localhost:9090/api/v1/query?query=up
```

### **Log Analysis**
```bash
# Access Kibana for log analysis
http://localhost:5601

# Search application logs
http://localhost:5601/app/discover
```

## 💾 **Backup & Recovery**

### **Database Backups**
```bash
# PostgreSQL backup
docker-compose -f docker-compose.production.yml exec postgres-primary \
  pg_dump -U trading_user trading > backup_$(date +%Y%m%d).sql

# Redis backup
docker-compose -f docker-compose.production.yml exec redis \
  redis-cli BGSAVE
```

### **Volume Backups**
```bash
# Backup persistent volumes
docker run --rm -v trade_discovery_postgres_primary_data:/data \
  -v $(pwd)/backups:/backup \
  alpine tar czf /backup/postgres_$(date +%Y%m%d).tar.gz -C /data .
```

## 🚀 **Production Deployment**

### **System Requirements**
```yaml
Production Server:
  CPU: 16+ cores
  RAM: 32GB+
  Storage: 500GB+ SSD
  Network: 1Gbps+
  
Development:
  CPU: 8+ cores  
  RAM: 16GB+
  Storage: 100GB+ SSD
```

### **Production Checklist**
- [ ] Strong passwords configured
- [ ] SSL certificates installed
- [ ] Firewall rules configured
- [ ] Monitoring alerts setup
- [ ] Backup procedures tested
- [ ] Log retention configured
- [ ] Performance baselines established
- [ ] Disaster recovery plan documented

## 📞 **Support**

### **Useful Commands**
```bash
# View all container status
docker-compose -f docker-compose.production.yml ps

# Restart unhealthy services
docker-compose -f docker-compose.production.yml restart

# Clean up resources
docker system prune -a --volumes

# Export metrics
curl http://localhost:9090/api/v1/query?query=up > metrics.json
```

### **Getting Help**
1. Check service logs: `docker-compose logs [service-name]`
2. Verify health endpoints: `curl http://localhost:8000/health`
3. Check Grafana dashboards for performance issues
4. Review Prometheus alerts
5. Analyze logs in Kibana

---

🎉 **Your production-grade trading platform infrastructure is now ready!**

For additional configuration and advanced features, refer to the individual service documentation in the `config/` directory. 
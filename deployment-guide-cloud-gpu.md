# Production-Grade Monitoring Stack Deployment Guide
## Shadeform Cloud GPU Instance Deployment

### 🚀 **Deployment Architecture Overview**

```
┌─────────────────────────────────────────────────────────────────┐
│                    CLOUD GPU INSTANCE                          │
│  ┌───────────────┐  ┌───────────────┐  ┌───────────────┐     │
│  │  Prometheus   │  │    Grafana    │  │    Jaeger     │     │
│  │   4GB RAM     │  │   2GB RAM     │  │   2GB RAM     │     │
│  │   2 CPU       │  │   1 CPU       │  │   1 CPU       │     │
│  │   Port 9090   │  │   Port 3000   │  │   Port 16686  │     │
│  └───────────────┘  └───────────────┘  └───────────────┘     │
│                                                               │
│  ┌───────────────┐  ┌───────────────┐                       │
│  │   cAdvisor    │  │  Alertmanager │                       │
│  │   512MB RAM   │  │   512MB RAM   │                       │
│  │   0.5 CPU     │  │   0.5 CPU     │                       │
│  │   Port 8082   │  │   Port 9093   │                       │
│  └───────────────┘  └───────────────┘                       │
│                                                               │
│  Total Resources: ~9GB RAM, ~5.5 CPU cores                   │
└─────────────────────────────────────────────────────────────────┘
                                │
                                │ SSH Connection
                                │
                    ┌─────────────────────┐
                    │   Your Laptop       │
                    │ (Development Env)   │
                    └─────────────────────┘
```

---

## 📋 **Prerequisites**

### **1. Cloud GPU Instance Requirements**
- **Minimum Specs**: 16GB RAM, 8 CPU cores, 100GB storage
- **Recommended**: NVIDIA GPU instances (for future ML workloads)
- **OS**: Ubuntu 20.04/22.04 LTS
- **Docker**: Version 20.10+
- **Docker Compose**: Version 2.0+

### **2. Network Configuration**
```bash
# Required open ports on cloud instance
22    (SSH)
3000  (Grafana UI)
9090  (Prometheus UI)
9093  (Alertmanager UI)
16686 (Jaeger UI)
8082  (cAdvisor metrics)
4317  (OTLP gRPC)
4318  (OTLP HTTP)
```

---

## 🔧 **Step 1: Initial Cloud Instance Setup**

### **Connect to Your Cloud Instance**
```bash
# SSH into your Shadeform GPU instance
ssh -i ~/.ssh/your-key.pem ubuntu@your-instance-ip

# Update system packages
sudo apt update && sudo apt upgrade -y

# Install Docker and Docker Compose
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker ubuntu

# Install Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# Logout and login again for Docker group changes
exit
ssh -i ~/.ssh/your-key.pem ubuntu@your-instance-ip
```

### **Verify Installation**
```bash
docker --version
docker-compose --version
docker run hello-world
```

---

## 📂 **Step 2: Transfer Project Files**

### **Method 1: Direct Git Clone (Recommended)**
```bash
# On cloud instance
git clone https://github.com/your-username/trade_discovery.git
cd trade_discovery

# Or if you have a private repo
git clone https://your-username:your-token@github.com/your-username/trade_discovery.git
cd trade_discovery
```

### **Method 2: SCP Transfer from Laptop**
```bash
# From your laptop - transfer entire project
scp -i ~/.ssh/your-key.pem -r /d/verities/trade/trade_discovery ubuntu@your-instance-ip:~/

# Or transfer specific monitoring files
scp -i ~/.ssh/your-key.pem docker-compose.monitoring.yml ubuntu@your-instance-ip:~/trade_discovery/
scp -i ~/.ssh/your-key.pem -r config/ ubuntu@your-instance-ip:~/trade_discovery/
scp -i ~/.ssh/your-key.pem -r tests/ ubuntu@your-instance-ip:~/trade_discovery/
```

### **Method 3: Rsync (Most Efficient)**
```bash
# From your laptop - sync entire project
rsync -avz -e "ssh -i ~/.ssh/your-key.pem" \
  /d/verities/trade/trade_discovery/ \
  ubuntu@your-instance-ip:~/trade_discovery/

# Exclude unnecessary files
rsync -avz -e "ssh -i ~/.ssh/your-key.pem" \
  --exclude 'node_modules' --exclude '.git' --exclude 'venv' \
  /d/verities/trade/trade_discovery/ \
  ubuntu@your-instance-ip:~/trade_discovery/
```

---

## 🔐 **Step 3: Production Environment Configuration**

### **Create Production Environment File**
```bash
# On cloud instance
cd ~/trade_discovery

# Create production environment file
cat > .env.production << EOF
# Production Environment Configuration
# ====================================

# Security - CHANGE THESE IN PRODUCTION!
GRAFANA_ADMIN_PASSWORD=YourSecurePassword2024!
GRAFANA_SECRET_KEY=$(openssl rand -base64 32)

# SSL/TLS Configuration (configure for HTTPS)
GRAFANA_PROTOCOL=https
GRAFANA_DOMAIN=your-monitoring.domain.com
GRAFANA_CERT_FILE=/etc/ssl/certs/grafana.crt
GRAFANA_CERT_KEY=/etc/ssl/private/grafana.key

# Security Headers
GRAFANA_COOKIE_SECURE=true
GRAFANA_HSTS=true

# Prometheus Configuration
PROMETHEUS_RETENTION_TIME=30d
PROMETHEUS_RETENTION_SIZE=100GB

# Logging
GRAFANA_LOG_LEVEL=info

# Production Features
ENVIRONMENT=production
DEBUG=false
LOG_LEVEL=INFO
EOF

# Set secure permissions
chmod 600 .env.production
```

### **SSL Certificate Setup (Optional but Recommended)**
```bash
# Option 1: Self-signed certificates (for testing)
sudo mkdir -p /etc/ssl/certs /etc/ssl/private
sudo openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout /etc/ssl/private/grafana.key \
  -out /etc/ssl/certs/grafana.crt \
  -subj "/C=US/ST=State/L=City/O=Organization/CN=your-monitoring.domain.com"

# Option 2: Let's Encrypt (for production domains)
sudo apt install certbot -y
sudo certbot certonly --standalone -d your-monitoring.domain.com
sudo ln -s /etc/letsencrypt/live/your-monitoring.domain.com/fullchain.pem /etc/ssl/certs/grafana.crt
sudo ln -s /etc/letsencrypt/live/your-monitoring.domain.com/privkey.pem /etc/ssl/private/grafana.key
```

---

## 🚀 **Step 4: Deploy Production Monitoring Stack**

### **Install Python Dependencies**
```bash
cd ~/trade_discovery

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install requirements
pip install -r requirements.txt
```

### **Start Production Stack**
```bash
# Load production environment
export $(cat .env.production | xargs)

# Deploy monitoring stack
docker-compose -f docker-compose.monitoring.yml up -d

# Verify all services are running
docker ps --filter "label=org.label-schema.group=monitoring"

# Check logs
docker-compose -f docker-compose.monitoring.yml logs -f
```

### **Monitor Resource Usage**
```bash
# Real-time resource monitoring
docker stats

# Check system resources
htop
free -h
df -h
```

---

## ✅ **Step 5: Run Production Tests**

```bash
# Activate virtual environment
source ~/trade_discovery/venv/bin/activate

# Run comprehensive test suite
python -m pytest tests/test_monitoring_infrastructure.py -v

# Run specific production tests
python -m pytest tests/test_monitoring_infrastructure.py::TestMonitoringInfrastructure::test_prometheus_service_accessible -v
python -m pytest tests/test_monitoring_infrastructure.py::TestMonitoringInfrastructure::test_grafana_service_accessible -v
```

---

## 🌐 **Step 6: Access Monitoring Services**

### **Set Up SSH Tunneling (Secure Access)**
```bash
# From your laptop - create SSH tunnels for secure access
ssh -i ~/.ssh/your-key.pem -L 3000:localhost:3000 \
    -L 9090:localhost:9090 \
    -L 16686:localhost:16686 \
    -L 9093:localhost:9093 \
    ubuntu@your-instance-ip
```

### **Access URLs (via SSH tunnel)**
- **Grafana**: http://localhost:3000 (admin / YourSecurePassword2024!)
- **Prometheus**: http://localhost:9090
- **Jaeger**: http://localhost:16686  
- **Alertmanager**: http://localhost:9093

### **Direct Access (if firewall allows)**
- **Grafana**: https://your-instance-ip:3000
- **Prometheus**: http://your-instance-ip:9090
- **Jaeger**: http://your-instance-ip:16686
- **Alertmanager**: http://your-instance-ip:9093

---

## 🔧 **Step 7: Production Optimization**

### **Performance Tuning**
```bash
# Increase file limits for Prometheus
echo "prometheus soft nofile 65536" | sudo tee -a /etc/security/limits.conf
echo "prometheus hard nofile 65536" | sudo tee -a /etc/security/limits.conf

# Optimize Docker for production
sudo tee /etc/docker/daemon.json << EOF
{
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "10m",
    "max-file": "3"
  },
  "storage-driver": "overlay2",
  "storage-opts": [
    "overlay2.override_kernel_check=true"
  ]
}
EOF

sudo systemctl restart docker
```

### **Backup Strategy**
```bash
# Create backup script
cat > ~/backup-monitoring.sh << 'EOF'
#!/bin/bash
BACKUP_DIR="/home/ubuntu/monitoring-backups/$(date +%Y%m%d_%H%M%S)"
mkdir -p $BACKUP_DIR

# Backup Docker volumes
docker run --rm -v trade_discovery_prometheus_data:/source -v $BACKUP_DIR:/backup alpine tar czf /backup/prometheus_data.tar.gz -C /source .
docker run --rm -v trade_discovery_grafana_data:/source -v $BACKUP_DIR:/backup alpine tar czf /backup/grafana_data.tar.gz -C /source .
docker run --rm -v trade_discovery_jaeger_data:/source -v $BACKUP_DIR:/backup alpine tar czf /backup/jaeger_data.tar.gz -C /source .

# Backup configuration
cp -r /home/ubuntu/trade_discovery/config $BACKUP_DIR/
cp /home/ubuntu/trade_discovery/.env.production $BACKUP_DIR/

echo "Backup completed: $BACKUP_DIR"
EOF

chmod +x ~/backup-monitoring.sh

# Add to cron for daily backups
(crontab -l 2>/dev/null; echo "0 2 * * * /home/ubuntu/backup-monitoring.sh") | crontab -
```

---

## 📊 **Step 8: Monitoring and Alerting Setup**

### **Configure Alertmanager for Production**
```bash
# Update Alertmanager configuration for production notifications
cat > config/alertmanager/alertmanager.yml << 'EOF'
global:
  smtp_smarthost: 'smtp.gmail.com:587'
  smtp_from: 'alerts@yourcompany.com'
  smtp_auth_username: 'your-email@gmail.com'
  smtp_auth_password: 'your-app-password'

route:
  group_by: ['alertname']
  group_wait: 10s
  group_interval: 10s
  repeat_interval: 1h
  receiver: 'web.hook'

receivers:
- name: 'web.hook'
  email_configs:
  - to: 'admin@yourcompany.com'
    subject: 'TradeDiscovery Alert: {{ .GroupLabels.alertname }}'
    body: |
      {{ range .Alerts }}
      Alert: {{ .Annotations.summary }}
      Description: {{ .Annotations.description }}
      {{ end }}
  
  slack_configs:
  - api_url: 'YOUR_SLACK_WEBHOOK_URL'
    channel: '#alerts'
    title: 'TradeDiscovery Alert'
    text: '{{ range .Alerts }}{{ .Annotations.summary }}{{ end }}'
EOF

# Restart Alertmanager
docker-compose -f docker-compose.monitoring.yml restart alertmanager
```

---

## 🔒 **Security Best Practices**

### **Firewall Configuration**
```bash
# Configure UFW firewall
sudo ufw enable
sudo ufw allow ssh
sudo ufw allow 3000/tcp comment 'Grafana'
sudo ufw allow 9090/tcp comment 'Prometheus'
sudo ufw allow 16686/tcp comment 'Jaeger'
sudo ufw allow 9093/tcp comment 'Alertmanager'

# For production, restrict to specific IPs
sudo ufw delete allow 3000/tcp
sudo ufw allow from YOUR_OFFICE_IP to any port 3000
```

### **Nginx Reverse Proxy (Recommended)**
```bash
# Install Nginx
sudo apt install nginx -y

# Configure reverse proxy with SSL
sudo tee /etc/nginx/sites-available/monitoring << 'EOF'
server {
    listen 80;
    server_name your-monitoring.domain.com;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name your-monitoring.domain.com;

    ssl_certificate /etc/ssl/certs/grafana.crt;
    ssl_certificate_key /etc/ssl/private/grafana.key;

    location /grafana/ {
        proxy_pass http://localhost:3000/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    location /prometheus/ {
        proxy_pass http://localhost:9090/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    location /jaeger/ {
        proxy_pass http://localhost:16686/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
EOF

sudo ln -s /etc/nginx/sites-available/monitoring /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

---

## 🏁 **Final Verification**

### **Complete Production Test**
```bash
cd ~/trade_discovery
source venv/bin/activate

# Run full test suite
python -m pytest tests/test_monitoring_infrastructure.py -v --tb=short

# Expected output: 18/18 tests passed
```

### **Performance Benchmarks**
```bash
# Check response times
curl -w "@curl-format.txt" -o /dev/null -s http://localhost:9090/-/ready
curl -w "@curl-format.txt" -o /dev/null -s http://localhost:3000/api/health

# Create curl format file
cat > curl-format.txt << 'EOF'
     time_namelookup:  %{time_namelookup}
        time_connect:  %{time_connect}
     time_appconnect:  %{time_appconnect}
    time_pretransfer:  %{time_pretransfer}
       time_redirect:  %{time_redirect}
  time_starttransfer:  %{time_starttransfer}
                     ----------
          time_total:  %{time_total}
EOF
```

---

## 🎯 **Success Criteria**

✅ **All monitoring services running and healthy**  
✅ **18/18 tests passing (100% success rate)**  
✅ **Resource usage within acceptable limits (< 50% of instance capacity)**  
✅ **Response times < 500ms for all services**  
✅ **Persistent data storage configured**  
✅ **Security configurations in place**  
✅ **Backup strategy implemented**  
✅ **Alerting configured for production**

---

## 🚀 **Next Steps**

1. **Custom Dashboards**: Import trading-specific Grafana dashboards
2. **Service Integration**: Connect your trading applications to send metrics
3. **Advanced Alerting**: Set up PagerDuty/Slack integrations
4. **Scaling**: Implement Prometheus federation for multi-instance deployments
5. **ML Integration**: Leverage GPU for real-time anomaly detection

---

**🎉 Congratulations! You now have a production-grade monitoring stack running on your cloud GPU instance!** 
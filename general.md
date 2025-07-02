# Cloud Instance & API Key Management Guide
*Last updated: July 2, 2023*

## 🔑 API Keys & Credentials

| Service | API Key/Token | Expiration | Notes |
|---------|--------------|------------|-------|
| Shadeform GPU | `<your-shadeform-api-key>` | YYYY-MM-DD | Used for programmatic instance creation |
| Docker Hub | `<your-dockerhub-token>` | YYYY-MM-DD | For private image pulls |
| Prometheus | `<prometheus-basic-auth>` | N/A | Basic auth for remote write |
| Grafana | `<grafana-api-key>` | N/A | For dashboard automation |
| Jaeger | `<jaeger-auth-token>` | N/A | For trace collection |
| Alertmanager | `<alertmanager-webhook-key>` | N/A | For alert notifications |
| SMTP Server | `<smtp-password>` | N/A | For email alerts |
| Slack Webhook | `<slack-webhook-url>` | N/A | For alert notifications |

## 🖥️ Cloud Instance Details

### Current Production Instances

| Name | IP Address | SSH Key | Purpose | Resources | Monthly Cost |
|------|------------|---------|---------|-----------|--------------|
| trade-monitoring | 203.0.113.10 | `~/.ssh/shadeform-key.pem` | Monitoring Stack | 16GB RAM, 8 vCPU | $XX.XX |
| trade-discovery | 203.0.113.11 | `~/.ssh/shadeform-key.pem` | Discovery Agents | 32GB RAM, 16 vCPU, 1 GPU | $XX.XX |
| trade-execution | 203.0.113.12 | `~/.ssh/shadeform-key.pem` | Execution Engine | 64GB RAM, 32 vCPU | $XX.XX |
| trade-database | 203.0.113.13 | `~/.ssh/shadeform-key.pem` | TimescaleDB | 32GB RAM, 16 vCPU | $XX.XX |

### Instance Creation Commands

```bash
# Create a new Shadeform GPU instance
shadeform create instance \
  --name trade-discovery-new \
  --instance-type gpu.4xlarge \
  --image ubuntu-22.04 \
  --region us-east-1 \
  --ssh-key ~/.ssh/shadeform-key.pem

# Alternative: AWS EC2 GPU instance
aws ec2 run-instances \
  --image-id ami-0c55b159cbfafe1f0 \
  --instance-type g4dn.xlarge \
  --key-name shadeform-key \
  --security-group-ids sg-0123456789abcdef0
```

## 🐳 Docker Configuration

### Registry Authentication

```bash
# Login to Docker Hub
docker login -u <username> -p <password>

# Login to private registry
docker login <registry-url> -u <username> -p <password>
```

### Production Environment Variables

Create `.env.production` files with these variables:

```
# Security
GRAFANA_ADMIN_PASSWORD=<strong-password>
GRAFANA_SECRET_KEY=<32-char-secret>

# SSL/TLS
GRAFANA_PROTOCOL=https
GRAFANA_DOMAIN=<your-domain>
GRAFANA_CERT_FILE=/etc/ssl/certs/grafana.crt
GRAFANA_CERT_KEY=/etc/ssl/private/grafana.key

# Prometheus
PROMETHEUS_RETENTION_TIME=30d
PROMETHEUS_RETENTION_SIZE=100GB

# Logging & Features
GRAFANA_LOG_LEVEL=info
ENVIRONMENT=production
DEBUG=false
LOG_LEVEL=INFO

# MinIO (for immutable audit logging)
MINIO_ROOT_USER=<minio-admin-user>
MINIO_ROOT_PASSWORD=<strong-minio-password>
MINIO_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY=<access-key>
MINIO_SECRET_KEY=<secret-key>
MINIO_USE_SSL=false
AUDIT_HMAC_SECRET=<32-char-audit-hmac-secret>
```

### Common Docker Commands

```bash
# Check container status
docker ps --filter "label=org.label-schema.group=monitoring"

# View container logs
docker logs <container-name>

# Restart services
docker-compose -f docker-compose.monitoring.yml restart

# Update services
docker-compose -f docker-compose.monitoring.yml pull && docker-compose -f docker-compose.monitoring.yml up -d

# Check resource usage
docker stats --no-stream
```

## 🔄 Deployment Process

### Monitoring Stack Deployment

1. Ensure SSH key is configured: `chmod 600 ~/.ssh/shadeform-key.pem`
2. Run deployment script: `./deploy-to-cloud.sh <instance-ip> ~/.ssh/shadeform-key.pem`
3. Set up SSH tunnel: 
   ```bash
   ssh -i ~/.ssh/shadeform-key.pem -L 3000:localhost:3000 -L 9090:localhost:9090 \
       -L 16686:localhost:16686 -L 9093:localhost:9093 ubuntu@<instance-ip>
   ```
4. Access services:
   - Grafana: http://localhost:3000 (admin / TradeDiscovery2024SecureAdmin!)
   - Prometheus: http://localhost:9090
   - Jaeger: http://localhost:16686
   - Alertmanager: http://localhost:9093

### Discovery Cluster Deployment

```bash
# Deploy discovery cluster
./deploy-discovery.sh <instance-ip> ~/.ssh/shadeform-key.pem
```

### Execution Cluster Deployment

```bash
# Deploy execution cluster
./deploy-execution.sh <instance-ip> ~/.ssh/shadeform-key.pem
```

## 🔒 Security Configuration

### Firewall Rules

```bash
# Configure UFW firewall
sudo ufw enable
sudo ufw allow ssh
sudo ufw allow 3000/tcp comment 'Grafana'
sudo ufw allow 9090/tcp comment 'Prometheus'
sudo ufw allow 16686/tcp comment 'Jaeger'
sudo ufw allow 9093/tcp comment 'Alertmanager'

# Restrict to specific IPs
sudo ufw delete allow 3000/tcp
sudo ufw allow from <your-office-ip> to any port 3000
```

### SSL Certificate Setup

```bash
# Option 1: Self-signed certificates
sudo mkdir -p /etc/ssl/certs /etc/ssl/private
sudo openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout /etc/ssl/private/grafana.key \
  -out /etc/ssl/certs/grafana.crt \
  -subj "/C=US/ST=State/L=City/O=Organization/CN=your-monitoring.domain.com"

# Option 2: Let's Encrypt
sudo apt install certbot -y
sudo certbot certonly --standalone -d your-monitoring.domain.com
sudo ln -s /etc/letsencrypt/live/your-monitoring.domain.com/fullchain.pem /etc/ssl/certs/grafana.crt
sudo ln -s /etc/letsencrypt/live/your-monitoring.domain.com/privkey.pem /etc/ssl/private/grafana.key
```

## 📊 Monitoring & Maintenance

### Backup Strategy

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

### Performance Tuning

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

## 🚨 Troubleshooting

### Common Issues & Solutions

1. **Container exits after startup**
   - Check logs: `docker logs <container-name>`
   - Check resource usage: `free -h`, `df -h`
   - Increase instance size if OOM kills occur

2. **Permission denied errors**
   - Fix ownership: 
     ```bash
     sudo chown -R 1000:1000 ~/trade_discovery/data/prometheus
     sudo chown -R 472:472 ~/trade_discovery/data/grafana
     ```

3. **Port conflicts**
   - Check used ports: `sudo netstat -tulpn | grep LISTEN`
   - Change port mappings in docker-compose.yml if needed

4. **Network connectivity issues**
   - Check Docker network: `docker network inspect trade_discovery_monitoring`
   - Verify container DNS: `docker exec -it prometheus cat /etc/resolv.conf`

5. **SSL/TLS certificate errors**
   - Verify certificate paths and permissions
   - Check certificate expiration: `openssl x509 -in /etc/ssl/certs/grafana.crt -text -noout | grep "Not After"`

## 📝 Notes & Updates

- **2023-07-01**: Initial setup of monitoring stack on Shadeform GPU instance
- **2023-07-02**: Added Alertmanager email notifications
- **2023-07-03**: Configured Slack integration for alerts

---

*This document is automatically updated when new configurations or API keys are added to the system.* 
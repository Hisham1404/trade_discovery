#!/bin/bash

# Discovery Cluster Health Check Script
# Comprehensive monitoring and health verification

set -e

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Health check configuration
TIMEOUT=5
RETRY_COUNT=3
HEALTH_SCORE=0
TOTAL_CHECKS=0

echo -e "${CYAN}Discovery Cluster Health Check${NC}"
echo -e "${CYAN}=============================${NC}"
echo ""

# Function to check service health
check_service() {
    local service_name="$1"
    local url="$2"
    local expected_status="$3"
    local description="$4"
    
    echo -n "Checking $service_name ($description)... "
    TOTAL_CHECKS=$((TOTAL_CHECKS + 1))
    
    for i in $(seq 1 $RETRY_COUNT); do
        if curl -sf --max-time $TIMEOUT "$url" > /dev/null 2>&1; then
            if [ -n "$expected_status" ]; then
                status=$(curl -s --max-time $TIMEOUT "$url" | jq -r '.status // empty' 2>/dev/null || echo "")
                if [ "$status" = "$expected_status" ] || [ -z "$expected_status" ]; then
                    echo -e "${GREEN}✓ HEALTHY${NC}"
                    HEALTH_SCORE=$((HEALTH_SCORE + 1))
                    return 0
                fi
            else
                echo -e "${GREEN}✓ HEALTHY${NC}"
                HEALTH_SCORE=$((HEALTH_SCORE + 1))
                return 0
            fi
        fi
        
        if [ $i -lt $RETRY_COUNT ]; then
            sleep 1
        fi
    done
    
    echo -e "${RED}✗ UNHEALTHY${NC}"
    return 1
}

# Function to check database
check_database() {
    echo -n "Checking PostgreSQL/TimescaleDB... "
    TOTAL_CHECKS=$((TOTAL_CHECKS + 1))
    
    if docker-compose exec -T postgres pg_isready -U discovery_user -d discovery_cluster > /dev/null 2>&1; then
        # Check if TimescaleDB extension is available
        if docker-compose exec -T postgres psql -U discovery_user -d discovery_cluster -c "SELECT 1 FROM pg_extension WHERE extname='timescaledb';" | grep -q "1"; then
            echo -e "${GREEN}✓ HEALTHY (TimescaleDB enabled)${NC}"
            HEALTH_SCORE=$((HEALTH_SCORE + 1))
        else
            echo -e "${YELLOW}! WARNING (TimescaleDB not enabled)${NC}"
        fi
    else
        echo -e "${RED}✗ UNHEALTHY${NC}"
    fi
}

# Function to check Redis
check_redis() {
    echo -n "Checking Redis... "
    TOTAL_CHECKS=$((TOTAL_CHECKS + 1))
    
    if docker-compose exec -T redis redis-cli ping | grep -q "PONG"; then
        echo -e "${GREEN}✓ HEALTHY${NC}"
        HEALTH_SCORE=$((HEALTH_SCORE + 1))
    else
        echo -e "${RED}✗ UNHEALTHY${NC}"
    fi
}

# Function to check container status
check_containers() {
    echo -e "\n${BLUE}Container Status:${NC}"
    echo "=================="
    
    services=("postgres" "redis" "pulsar" "qdrant" "elasticsearch" "minio" "prometheus" "grafana" "jaeger")
    
    for service in "${services[@]}"; do
        TOTAL_CHECKS=$((TOTAL_CHECKS + 1))
        container_status=$(docker-compose ps -q $service | xargs docker inspect --format='{{.State.Status}}' 2>/dev/null || echo "not_found")
        
        case $container_status in
            "running")
                echo -e "$service: ${GREEN}✓ RUNNING${NC}"
                HEALTH_SCORE=$((HEALTH_SCORE + 1))
                ;;
            "exited")
                echo -e "$service: ${RED}✗ EXITED${NC}"
                ;;
            "not_found")
                echo -e "$service: ${YELLOW}! NOT FOUND${NC}"
                ;;
            *)
                echo -e "$service: ${YELLOW}! $container_status${NC}"
                ;;
        esac
    done
}

# Function to check service endpoints
check_endpoints() {
    echo -e "\n${BLUE}Service Endpoints:${NC}"
    echo "=================="
    
    # Core infrastructure services
    check_service "Elasticsearch" "http://localhost:9200/_cluster/health" "green" "Search engine cluster health"
    check_service "Qdrant" "http://localhost:6333/health" "" "Vector database health"
    check_service "MinIO" "http://localhost:9000/minio/health/live" "" "Object storage health"
    check_service "Prometheus" "http://localhost:9090/-/healthy" "" "Metrics collection health"
    check_service "Grafana" "http://localhost:3000/api/health" "" "Dashboard service health"
    check_service "Jaeger" "http://localhost:16686/" "" "Tracing service health"
    check_service "Pulsar Admin" "http://localhost:8080/admin/v2/brokers/health" "" "Message broker health"
}

# Function to check data integrity
check_data_integrity() {
    echo -e "\n${BLUE}Data Integrity:${NC}"
    echo "==============="
    
    echo -n "Checking sample trading signals... "
    TOTAL_CHECKS=$((TOTAL_CHECKS + 1))
    
    signal_count=$(docker-compose exec -T postgres psql -U discovery_user -d discovery_cluster -t -c "SELECT COUNT(*) FROM trading.signals;" 2>/dev/null | tr -d ' \n' || echo "0")
    
    if [ "$signal_count" -gt "0" ]; then
        echo -e "${GREEN}✓ $signal_count signals found${NC}"
        HEALTH_SCORE=$((HEALTH_SCORE + 1))
    else
        echo -e "${YELLOW}! No signals found (expected for new installation)${NC}"
    fi
    
    echo -n "Checking monitoring events... "
    TOTAL_CHECKS=$((TOTAL_CHECKS + 1))
    
    event_count=$(docker-compose exec -T postgres psql -U discovery_user -d discovery_cluster -t -c "SELECT COUNT(*) FROM monitoring.events;" 2>/dev/null | tr -d ' \n' || echo "0")
    
    if [ "$event_count" -gt "0" ]; then
        echo -e "${GREEN}✓ $event_count events found${NC}"
        HEALTH_SCORE=$((HEALTH_SCORE + 1))
    else
        echo -e "${YELLOW}! No events found${NC}"
    fi
}

# Function to check resource usage
check_resources() {
    echo -e "\n${BLUE}Resource Usage:${NC}"
    echo "==============="
    
    echo "Docker system info:"
    docker system df --format "table {{.Type}}\t{{.TotalCount}}\t{{.Size}}\t{{.Reclaimable}}"
    
    echo -e "\nContainer resource usage:"
    docker stats --no-stream --format "table {{.Container}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.MemPerc}}" $(docker-compose ps -q) 2>/dev/null || echo "No containers running"
}

# Function to generate health summary
generate_summary() {
    echo -e "\n${CYAN}Health Summary:${NC}"
    echo "=============="
    
    health_percentage=$((HEALTH_SCORE * 100 / TOTAL_CHECKS))
    
    if [ $health_percentage -ge 90 ]; then
        status_color=$GREEN
        status_text="EXCELLENT"
    elif [ $health_percentage -ge 70 ]; then
        status_color=$YELLOW
        status_text="GOOD"
    elif [ $health_percentage -ge 50 ]; then
        status_color=$YELLOW
        status_text="FAIR"
    else
        status_color=$RED
        status_text="POOR"
    fi
    
    echo -e "Overall Health: ${status_color}$status_text ($HEALTH_SCORE/$TOTAL_CHECKS checks passed - $health_percentage%)${NC}"
    
    if [ $health_percentage -lt 100 ]; then
        echo -e "${YELLOW}Recommendations:${NC}"
        echo "- Check failed services and restart if necessary"
        echo "- Review logs with: docker-compose logs <service_name>"
        echo "- Ensure all required environment variables are set"
        echo "- Verify sufficient system resources are available"
    fi
    
    echo -e "\n${BLUE}Quick Access URLs:${NC}"
    echo "- Grafana Dashboard: http://localhost:3000 (admin/admin123)"
    echo "- Prometheus: http://localhost:9090"
    echo "- Jaeger Tracing: http://localhost:16686"
    echo "- MinIO Console: http://localhost:9001 (minioadmin/minioadmin123)"
    echo "- Elasticsearch: http://localhost:9200"
}

# Main execution
main() {
    # Check if Docker Compose is running
    if ! docker-compose ps > /dev/null 2>&1; then
        echo -e "${RED}Error: Docker Compose services not found. Please start services first.${NC}"
        echo "Run: docker-compose up -d"
        exit 1
    fi
    
    # Perform all health checks
    check_containers
    check_database
    check_redis
    check_endpoints
    check_data_integrity
    check_resources
    generate_summary
    
    # Exit with error code if health is poor
    health_percentage=$((HEALTH_SCORE * 100 / TOTAL_CHECKS))
    if [ $health_percentage -lt 70 ]; then
        exit 1
    fi
}

# Check if required tools are available
if ! command -v curl &> /dev/null; then
    echo -e "${YELLOW}Warning: curl not found. Some health checks may fail.${NC}"
fi

if ! command -v jq &> /dev/null; then
    echo -e "${YELLOW}Warning: jq not found. JSON parsing will be limited.${NC}"
fi

# Run main function
main 
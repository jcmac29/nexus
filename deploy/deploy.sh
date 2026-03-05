#!/bin/bash
# Nexus Production Deployment Script
# Usage: ./deploy/deploy.sh

set -e

echo "=========================================="
echo "Nexus Production Deployment"
echo "=========================================="

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check for required environment variables
check_env() {
    echo -e "${YELLOW}Checking environment variables...${NC}"
    
    required_vars=(
        "SECRET_KEY"
        "ADMIN_JWT_SECRET"
        "DB_PASSWORD"
        "STORAGE_SECRET_KEY"
    )
    
    missing=()
    for var in "${required_vars[@]}"; do
        if [ -z "${!var}" ]; then
            missing+=("$var")
        fi
    done
    
    if [ ${#missing[@]} -ne 0 ]; then
        echo -e "${RED}ERROR: Missing required environment variables:${NC}"
        printf '  - %s\n' "${missing[@]}"
        echo ""
        echo "Create a .env file with these variables or export them:"
        echo "  cp .env.example .env && nano .env"
        exit 1
    fi
    
    echo -e "${GREEN}All required environment variables set.${NC}"
}

# Generate secure secrets if not set
generate_secrets() {
    echo -e "${YELLOW}Generating secure secrets...${NC}"
    
    if [ -z "$SECRET_KEY" ]; then
        export SECRET_KEY=$(openssl rand -base64 32)
        echo "SECRET_KEY=$SECRET_KEY" >> .env
    fi
    
    if [ -z "$ADMIN_JWT_SECRET" ]; then
        export ADMIN_JWT_SECRET=$(openssl rand -base64 32)
        echo "ADMIN_JWT_SECRET=$ADMIN_JWT_SECRET" >> .env
    fi
    
    if [ -z "$DB_PASSWORD" ]; then
        export DB_PASSWORD=$(openssl rand -base64 24)
        echo "DB_PASSWORD=$DB_PASSWORD" >> .env
    fi
    
    if [ -z "$STORAGE_SECRET_KEY" ]; then
        export STORAGE_SECRET_KEY=$(openssl rand -base64 32)
        echo "STORAGE_SECRET_KEY=$STORAGE_SECRET_KEY" >> .env
    fi
    
    echo -e "${GREEN}Secrets generated and saved to .env${NC}"
}

# Build and deploy
deploy() {
    echo -e "${YELLOW}Building and deploying services...${NC}"
    
    # Pull latest images
    docker compose -f docker-compose.prod.yml pull
    
    # Build custom images
    docker compose -f docker-compose.prod.yml build
    
    # Start services
    docker compose -f docker-compose.prod.yml up -d
    
    echo -e "${GREEN}Services started successfully.${NC}"
}

# Run database migrations
migrate() {
    echo -e "${YELLOW}Running database migrations...${NC}"
    docker compose -f docker-compose.prod.yml exec api alembic upgrade head
    echo -e "${GREEN}Migrations complete.${NC}"
}

# Health check
health_check() {
    echo -e "${YELLOW}Checking service health...${NC}"
    
    sleep 10  # Wait for services to start
    
    services=("api" "admin-dashboard" "landing" "playground" "user-dashboard" "nginx" "db" "redis" "minio")
    
    for service in "${services[@]}"; do
        status=$(docker compose -f docker-compose.prod.yml ps --format '{{.Status}}' $service 2>/dev/null || echo "Not running")
        if [[ "$status" == *"Up"* ]] || [[ "$status" == *"healthy"* ]]; then
            echo -e "  ${GREEN}✓${NC} $service: $status"
        else
            echo -e "  ${RED}✗${NC} $service: $status"
        fi
    done
}

# Main deployment flow
main() {
    # Load .env if exists
    if [ -f .env ]; then
        export $(cat .env | grep -v '^#' | xargs)
    fi
    
    case "${1:-deploy}" in
        "init")
            generate_secrets
            deploy
            migrate
            health_check
            ;;
        "deploy")
            check_env
            deploy
            health_check
            ;;
        "migrate")
            migrate
            ;;
        "health")
            health_check
            ;;
        "logs")
            docker compose -f docker-compose.prod.yml logs -f ${2:-}
            ;;
        "stop")
            docker compose -f docker-compose.prod.yml down
            ;;
        "restart")
            docker compose -f docker-compose.prod.yml restart ${2:-}
            ;;
        *)
            echo "Usage: $0 {init|deploy|migrate|health|logs|stop|restart}"
            exit 1
            ;;
    esac
    
    echo ""
    echo "=========================================="
    echo -e "${GREEN}Deployment complete!${NC}"
    echo "=========================================="
    echo ""
    echo "Access your services:"
    echo "  Landing:    http://your-domain/"
    echo "  Dashboard:  http://your-domain/dashboard"
    echo "  Admin:      http://your-domain/admin"
    echo "  API:        http://your-domain/api/v1"
    echo "  Playground: http://your-domain/playground"
    echo ""
}

main "$@"

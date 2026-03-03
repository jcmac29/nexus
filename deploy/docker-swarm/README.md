# Docker Swarm Deployment

Deploy Nexus to a Docker Swarm cluster.

## Prerequisites

- Docker Swarm cluster initialized
- At least one manager node

## Setup

### 1. Initialize Swarm (if not already done)

```bash
docker swarm init
```

### 2. Create Secrets

```bash
# Generate secure values
echo "your-secret-key" | docker secret create secret_key -
echo "nexus" | docker secret create postgres_password -
echo "minioadmin" | docker secret create minio_access_key -
echo "minioadmin" | docker secret create minio_secret_key -
echo "sk-your-stripe-key" | docker secret create stripe_secret_key -
echo "sk-your-openai-key" | docker secret create openai_api_key -
echo "admin" | docker secret create grafana_password -
```

### 3. Build and Push Image

```bash
# Build the image
docker build -t nexus-api:latest ./core

# If using a registry
docker tag nexus-api:latest your-registry/nexus-api:latest
docker push your-registry/nexus-api:latest
```

### 4. Deploy Stack

```bash
docker stack deploy -c docker-stack.yml nexus
```

### 5. Verify Deployment

```bash
# Check services
docker stack services nexus

# Check service logs
docker service logs nexus_nexus-api

# Scale API
docker service scale nexus_nexus-api=5
```

## Update Deployment

```bash
# Update a service
docker service update --image nexus-api:v2 nexus_nexus-api

# Full stack update
docker stack deploy -c docker-stack.yml nexus
```

## Rollback

```bash
docker service rollback nexus_nexus-api
```

## Remove Stack

```bash
docker stack rm nexus
```

## Monitoring

- Prometheus: http://prometheus.example.com
- Grafana: http://grafana.example.com (admin/your-password)

## Configuration

Update `docker-stack.yml` for:
- Domain names in Traefik labels
- Resource limits
- Replica counts
- Secret names

## Troubleshooting

```bash
# View service details
docker service inspect nexus_nexus-api

# View task distribution
docker service ps nexus_nexus-api

# Check node availability
docker node ls
```

.PHONY: help start stop restart logs shell-backend shell-db shell-redis clean build test

# Default target
help:
	@echo "Network Management Platform - Available Commands"
	@echo "================================================"
	@echo ""
	@echo "  make start          - Start all services"
	@echo "  make stop           - Stop all services"
	@echo "  make restart        - Restart all services"
	@echo "  make logs           - View logs from all services"
	@echo "  make logs-backend   - View backend logs only"
	@echo "  make logs-frontend  - View frontend logs only"
	@echo "  make shell-backend  - Open shell in backend container"
	@echo "  make shell-db       - Open PostgreSQL shell"
	@echo "  make shell-redis    - Open Redis CLI"
	@echo "  make build          - Rebuild all containers"
	@echo "  make clean          - Remove all containers and volumes"
	@echo "  make test           - Run backend tests"
	@echo "  make status         - Show status of all services"
	@echo "  make discover       - Run network discovery (192.168.1.0/24)"
	@echo "  make health-check   - Run health check on all devices"
	@echo ""

# Start all services
start:
	@echo "Starting Network Management Platform..."
	docker compose up -d
	@echo ""
	@echo "Services started successfully!"
	@echo "  Web Interface: http://localhost"
	@echo "  Backend API:   http://localhost:3000/api"
	@echo "  Database:      localhost:5432"
	@echo "  Redis:         localhost:6379"
	@echo ""
	@echo "Default login: admin / admin"

# Stop all services
stop:
	@echo "Stopping Network Management Platform..."
	docker compose down
	@echo "All services stopped."

# Restart all services
restart:
	@echo "Restarting Network Management Platform..."
	docker compose restart
	@echo "All services restarted."

# View logs
logs:
	docker compose logs -f

# View backend logs only
logs-backend:
	docker compose logs -f backend

# View frontend logs only
logs-frontend:
	docker compose logs -f frontend

# Open shell in backend container
shell-backend:
	docker compose exec backend /bin/sh

# Open PostgreSQL shell
shell-db:
	docker compose exec postgres psql -U network_user -d network_mgmt

# Open Redis CLI
shell-redis:
	docker compose exec redis redis-cli

# Rebuild all containers
build:
	@echo "Rebuilding all containers..."
	docker compose build --no-cache
	@echo "Build complete."

# Clean up all containers and volumes
clean:
	@echo "Cleaning up all containers and volumes..."
	docker compose down -v
	@echo "Cleanup complete."

# Run backend tests
test:
	@echo "Running backend tests..."
	docker compose exec backend npm test

# Show status of all services
status:
	docker compose ps

# Run network discovery
discover:
	@echo "Running network discovery on 192.168.1.0/24..."
	docker compose exec backend node -e "const { discoverNetwork } = require('./services/discovery'); discoverNetwork('192.168.1.0/24', { saveToDatabase: true, snmpCommunities: ['public', 'private'], timeout: 2000 }).then(devices => console.log(\`Found \${devices.length} devices\`)).catch(err => console.error('Error:', err.message))"

# Run health check on all devices
health-check:
	@echo "Running health check on all devices..."
	docker compose exec backend node -e "const { Device } = require('./models'); const { monitorDevices } = require('./services/monitoring'); Device.findAll().then(devices => { if (devices.length === 0) { console.log('No devices found'); return; } return monitorDevices(devices); }).then(results => console.log(\`Health check complete: \${results.length} devices checked\`)).catch(err => console.error('Error:', err.message))"
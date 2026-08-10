#!/bin/bash

# Network Management Platform - Getting Started Script
# This script will help you get the platform up and running

set -e

echo "=========================================="
echo "  Network Management Platform Setup"
echo "=========================================="
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo -e "${RED}Error: Docker is not installed${NC}"
    echo "Please install Docker first: https://docs.docker.com/get-docker/"
    exit 1
fi

# Check if Docker Compose is installed
if ! docker compose version &> /dev/null; then
    echo -e "${RED}Error: Docker Compose is not installed${NC}"
    echo "Please install Docker Compose: https://docs.docker.com/compose/install/"
    exit 1
fi

echo -e "${GREEN}✓ Docker is installed${NC}"
echo -e "${GREEN}✓ Docker Compose is installed${NC}"
echo ""

# Check if .env file exists
if [ ! -f .env ]; then
    echo -e "${YELLOW}Creating .env file from template...${NC}"
    cp .env.example .env
    echo -e "${GREEN}✓ .env file created${NC}"
    echo ""
    echo -e "${YELLOW}Please edit .env file and set the following variables:${NC}"
    echo "  - POSTGRES_PASSWORD: Strong password for PostgreSQL"
    echo "  - JWT_SECRET: Secret key for JWT tokens"
    echo ""
    echo "Example:"
    echo "  POSTGRES_PASSWORD=your_strong_password_here"
    echo "  JWT_SECRET=your_jwt_secret_here"
    echo ""
    read -p "Press Enter when .env is configured..."
fi

# Check if .env has weak passwords
if grep -q "your_" .env; then
    echo -e "${YELLOW}Warning: .env file contains default/weak values${NC}"
    echo "Please update the following in .env:"
    grep "your_" .env | sed 's/^/  - /'
    echo ""
    read -p "Press Enter to continue anyway or Ctrl+C to cancel..."
fi

# Start services
echo -e "${GREEN}Starting services...${NC}"
docker compose up -d

# Wait for services to be ready
echo -e "${YELLOW}Waiting for services to start...${NC}"
sleep 10

# Check if services are running
if docker compose ps | grep -q "Up"; then
    echo -e "${GREEN}✓ All services are running${NC}"
    echo ""
    echo "=========================================="
    echo "  Setup Complete!"
    echo "=========================================="
    echo ""
    echo "Access the application:"
    echo "  🌐 Web Interface: http://localhost"
    echo "  🔌 Backend API:   http://localhost:3000/api"
    echo "  🗄️ Database:      localhost:5432"
    echo "  💾 Redis:         localhost:6379"
    echo ""
    echo "Default Login:"
    echo "  Username: admin"
    echo "  Password: admin"
    echo ""
    echo "Next Steps:"
    echo "  1. Login to the web interface"
    echo "  2. Add your network devices"
    echo "  3. Run network discovery"
    echo "  4. Monitor device health"
    echo ""
    echo "Useful Commands:"
    echo "  make logs          - View logs from all services"
    echo "  make stop          - Stop all services"
    echo "  make restart       - Restart all services"
    echo "  make shell-backend - Open shell in backend container"
    echo "  make shell-db      - Open PostgreSQL shell"
    echo "  make discover      - Run network discovery"
    echo "  make health-check  - Run health check on all devices"
    echo ""
    echo "Documentation:"
    echo "  README.md          - Project overview"
    echo "  QUICKSTART.md      - Quick start guide"
    echo "  API.md             - API documentation"
    echo "  DEPLOYMENT.md      - Production deployment guide"
    echo ""
else
    echo -e "${RED}Error: Services failed to start${NC}"
    echo "Check logs with: docker compose logs"
    exit 1
fi
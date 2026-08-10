# Network Management Platform - Quick Start Guide

## 🚀 Getting Started in 5 Minutes

### 1. Clone and Setup
```bash
cd /home/ddias/network-mgmt-platform
cp .env.example .env
```

Edit `.env` with your preferences:
```bash
POSTGRES_PASSWORD=your_secure_password_here
JWT_SECRET=your_jwt_secret_here
DISCOVERY_NETWORK=192.168.1.0/24
```

### 2. Start All Services
```bash
docker-compose up -d
```

This will start:
- PostgreSQL database (port 5432)
- Redis cache (port 6379)
- Backend API (internal)
- Frontend web interface (port 80)
- Worker service for background tasks

### 3. Access the Application
Open your browser and navigate to:
- **Web Interface**: http://localhost
- **API Documentation**: http://localhost/api (when backend is running)

**Default Login:**
- Username: `admin`
- Password: `admin`

## 📋 What You Can Do Now

### Device Management
1. Go to **Devices** page
2. Click **Add Device**
3. Enter device details:
   - IP address
   - Vendor (Cisco, Palo Alto, Aruba, etc.)
   - SSH/Telnet credentials
   - SNMP community string

### Network Discovery
1. Go to **Network Discovery**
2. Enter network range (e.g., `192.168.1.0/24`)
3. Click **Start Discovery**
4. System will automatically:
   - Ping all IPs in range
   - Query SNMP for device info
   - Create device entries in database

### Device Monitoring
1. Go to **Monitoring** page
2. View real-time device health:
   - Ping status
   - SSH/Telnet/SNMP connectivity
   - CPU/Memory utilization
   - Interface statistics
3. Click **Run Health Check** for immediate status

### Execute Commands
1. Go to **Devices** page
2. Select a device
3. Click **Execute Command**
4. Enter CLI command (e.g., `show version`, `show interfaces`)
5. View output directly in the web interface

## 🔧 Common Tasks

### Add a Single Device
```bash
# Via API
curl -X POST http://localhost/api/devices \
  -H "Content-Type: application/json" \
  -H "x-auth-token: YOUR_TOKEN" \
  -d '{
    "hostname": "switch-01",
    "ip_address": "192.168.1.10",
    "vendor": "cisco",
    "device_type": "switch",
    "username": "admin",
    "password": "password123",
    "ssh_port": 22,
    "snmp_community": "public"
  }'
```

### Run Discovery
```bash
curl -X POST http://localhost/api/devices/discover \
  -H "Content-Type: application/json" \
  -H "x-auth-token: YOUR_TOKEN" \
  -d '{
    "network": "192.168.1.0/24",
    "snmp_communities": ["public", "private"],
    "timeout": 2000
  }'
```

### Execute Command on Device
```bash
curl -X POST http://localhost/api/devices/DEVICE_ID/execute-command \
  -H "Content-Type: application/json" \
  -H "x-auth-token: YOUR_TOKEN" \
  -d '{
    "command": "show version"
  }'
```

## 🛠️ Development Mode

### Run Backend Locally
```bash
cd backend
npm install
npm run dev
```

### Run Frontend Locally
```bash
cd frontend
npm install
npm run dev
```

### Run Tests
```bash
cd backend
npm test
```

## 📊 Architecture Overview

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  Frontend   │────▶│   Backend   │────▶│  PostgreSQL │
│  (React)    │     │  (Express)  │     │  Database   │
└─────────────┘     └─────────────┘     └─────────────┘
                           │
                           ▼
                    ┌─────────────┐
                    │    Redis    │
                    │   Cache     │
                    └─────────────┘
                           │
                           ▼
                    ┌─────────────┐
                    │   Worker    │
                    │  Service    │
                    └─────────────┘
                           │
              ┌────────────┼────────────┐
              ▼            ▼            ▼
         ┌────────┐  ┌────────┐  ┌────────┐
         │  SSH   │  │ SNMP   │  │Telnet  │
         └────────┘  └────────┘  └────────┘
```

## 🐛 Troubleshooting

### Services Not Starting
```bash
# Check logs
docker-compose logs -f

# Restart services
docker-compose restart

# Rebuild if needed
docker-compose down
docker-compose up -d --build
```

### Database Connection Issues
```bash
# Check if PostgreSQL is running
docker-compose ps

# Access database directly
docker exec -it network-mgmt-postgres psql -U network_user -d network_mgmt
```

### Discovery Not Finding Devices
- Verify network range is correct
- Check firewall rules
- Ensure SNMP is enabled on target devices
- Try different SNMP community strings

## 📚 Next Steps

1. **Configure Alerts**: Set up email/webhook notifications for device issues
2. **Add More Devices**: Import your entire network inventory
3. **Customize Dashboards**: Create custom views for different device types
4. **Integrate External Tools**: Connect with ticketing systems, monitoring tools
5. **Extend Functionality**: Add custom adapters for proprietary devices

## 🤝 Getting Help

- Check `README.md` for detailed documentation
- Review `backend/services/` for implementation details
- Examine `protocols/` for SSH/SNMP/Telnet implementations
- Look at `adapters/` for vendor-specific code

---

**Ready to manage your network!** 🎉

Start by adding your first device or running a network discovery to see the platform in action.
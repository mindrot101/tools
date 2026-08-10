# Network Management Platform

A Docker-based web application that replicates and extends SolarWinds Engineer's Toolset functionality for managing enterprise network equipment.

## Features

### Core Functionality
- **Device Management**: Add, edit, and manage network devices from various vendors (Cisco, Palo Alto, Aruba, Arista, Juniper, etc.)
- **Network Discovery**: Automatically discover devices on your network using ping sweeps and SNMP
- **Health Monitoring**: Check device connectivity via ping, SSH, Telnet, and SNMP
- **Performance Metrics**: Collect CPU, memory, and interface statistics via SNMP
- **Authentication**: User login/logout with role-based access control
- **Responsive Web Interface**: Modern React/Material-UI dashboard

### Supported Protocols
- **SSH**: Secure shell access for CLI interaction
- **Telnet**: Legacy terminal access
- **SNMP**: Network monitoring and discovery (v1, v2c, v3 planned)
- **ICMP/Ping**: Basic connectivity testing

### Supported Vendors
- Cisco (IOS, IOS-XE, IOS-XR, NX-OS)
- Palo Alto Networks (PAN-OS)
- Aruba (AOS-CX, AOS-S)
- Arista (EOS)
- Juniper (JunOS)
- And more via extensible adapter system

## Architecture

### Services
- **PostgreSQL**: Primary database for device inventory, configurations, and monitoring data
- **Redis**: Caching and message queuing (planned for real-time updates)
- **Backend API**: Node.js/Express server with REST endpoints
- **Worker Service**: Background tasks for discovery and monitoring
- **Frontend**: React/Vite application with Material-UI
- **NGINX**: Reverse proxy (optional)

### Key Components
- **Protocol Handlers**: SSH, Telnet, SNMP implementations
- **Discovery Service**: Network scanning and device identification
- **Monitoring Service**: Health checks and metric collection
- **Device Adapters**: Vendor-specific command handlers (extensible)
- **Web Interface**: Dashboard, device management, monitoring views

## Getting Started

### Prerequisites
- Docker and Docker Compose
- Git (optional)

### Installation

1. Clone the repository:
   ```bash
   git clone <repository-url>
   cd network-mgmt-platform
   ```

2. Copy the example environment file:
   ```bash
   cp .env.example .env
   ```

3. Edit `.env` to configure:
   - Database credentials
   - JWT secret
   - Discovery network range
   - Other service configurations

4. Start the services:
   ```bash
   docker-compose up -d
   ```

5. Access the web interface:
   - Frontend: http://localhost
   - Backend API: http://localhost:3000/api
   - PostgreSQL: localhost:5432
   - Redis: localhost:6379

### Default Login
- Username: `admin`
- Password: `admin`

## API Endpoints

### Authentication
- `POST /api/auth/register` - Register new user
- `POST /api/auth/login` - Login and get JWT token
- `GET /api/auth/me` - Get current user info

### Devices
- `GET /api/devices` - List all devices
- `GET /api/devices/:id` - Get device by ID
- `POST /api/devices` - Add new device
- `PUT /api/devices/:id` - Update device
- `DELETE /api/devices/:id` - Delete device
- `GET /api/devices/search/:term` - Search devices

## Development

### Backend
```bash
cd backend
npm install
npm run dev  # For development with nodemon
```

### Frontend
```bash
cd frontend
npm install
npm run dev  # For development with Vite
```

## Extending the Platform

### Adding New Protocol Support
1. Create a new file in `protocols/` (e.g., `netconf.js`)
2. Implement the protocol-specific logic
3. Export functions for connection, command execution, etc.
4. Import and use in services as needed

### Adding Vendor-Specific Features
1. Create a new adapter in `adapters/` (e.g., `cisco-asa.js`)
2. Implement vendor-specific command mappings and parsing
3. Use in monitoring or configuration services

### Adding New Metrics
1. Extend the `MonitoringService.collectMetrics()` method
2. Add new SNMP OID queries or CLI command parsing
3. Store results in the monitoring database table

## Future Enhancements

### Planned Features
- Configuration backup and version control
- Real-time monitoring with WebSocket updates
- Alerting and notification system (email, SMS, webhook)
- Network topology mapping
- Command execution and job scheduling
- Report generation and export
- LDAP/Active Directory integration
- Multi-tenancy support
- Plugin/extension system

### Protocol Improvements
- SNMP v3 support with authentication and encryption
- NETCONF/RESTCONF support for modern devices
- API integration with cloud providers (AWS, Azure, GCP)
- REST API vendors (Meraki, Cisco DNA Center, etc.)

## Security Considerations

### Current Implementation
- Passwords are hashed in the database (bcrypt)
- JWT-based authentication for API access
- Environment-based configuration for secrets
- Input validation on all API endpoints

### Recommended Production Enhancements
- Enable HTTPS with SSL certificates
- Implement rate limiting on API endpoints
- Use secrets management (HashiCorp Vault, AWS Secrets Manager)
- Regular security audits and penetration testing
- Network segmentation for management traffic
- MFA authentication options

## License

MIT License - see LICENSE file for details

## Acknowledgments

- Inspired by SolarWinds Engineer's Toolset
- Built with open-source technologies: Node.js, React, PostgreSQL, Redis
- Uses various open-source libraries for SSH, SNMP, Telnet, and UI components
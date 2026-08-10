# API Documentation

Base URL: `http://localhost:3000/api`

All endpoints (except authentication) require authentication via JWT token in the `x-auth-token` header.

## Authentication

### Register User
```http
POST /auth/register
Content-Type: application/json

{
  "username": "admin",
  "email": "admin@example.com",
  "password": "secure_password"
}
```

**Response:**
```json
{
  "user": {
    "id": "uuid",
    "username": "admin",
    "email": "admin@example.com",
    "role": "user"
  },
  "token": "jwt_token_here"
}
```

### Login
```http
POST /auth/login
Content-Type: application/json

{
  "username": "admin",
  "password": "admin"
}
```

**Response:**
```json
{
  "user": {
    "id": "uuid",
    "username": "admin",
    "email": "admin@example.com",
    "role": "admin"
  },
  "token": "jwt_token_here"
}
```

### Get Current User
```http
GET /auth/me
x-auth-token: jwt_token_here
```

**Response:**
```json
{
  "id": "uuid",
  "username": "admin",
  "email": "admin@example.com",
  "role": "admin"
}
```

## Devices

### List All Devices
```http
GET /devices
x-auth-token: jwt_token_here

# Optional query parameters:
# ?status=online|offline|unknown
# ?vendor=cisco|palo_alto|aruba|arista|juniper
# ?device_type=switch|router|firewall|access_point
# ?search=term
```

**Response:**
```json
[
  {
    "id": "uuid",
    "hostname": "core-switch-01",
    "ip_address": "192.168.1.1",
    "vendor": "cisco",
    "device_type": "switch",
    "username": "admin",
    "ssh_port": 22,
    "telnet_port": 23,
    "snmp_port": 161,
    "snmp_version": "2c",
    "snmp_community": "public",
    "status": "online",
    "last_seen": "2026-08-06T16:00:00.000Z",
    "notes": "Core distribution switch",
    "createdAt": "2026-08-06T12:00:00.000Z",
    "updatedAt": "2026-08-06T16:00:00.000Z"
  }
]
```

### Get Device by ID
```http
GET /devices/:id
x-auth-token: jwt_token_here
```

**Response:**
```json
{
  "id": "uuid",
  "hostname": "core-switch-01",
  "ip_address": "192.168.1.1",
  "vendor": "cisco",
  "device_type": "switch",
  ...
}
```

### Add New Device
```http
POST /devices
Content-Type: application/json
x-auth-token: jwt_token_here

{
  "hostname": "firewall-01",
  "ip_address": "192.168.1.254",
  "vendor": "palo_alto",
  "device_type": "firewall",
  "username": "admin",
  "password": "secure_password",
  "ssh_port": 22,
  "telnet_port": 23,
  "snmp_port": 161,
  "snmp_version": "2c",
  "snmp_community": "public",
  "notes": "Perimeter firewall"
}
```

**Response:**
```json
{
  "id": "uuid",
  "hostname": "firewall-01",
  "ip_address": "192.168.1.254",
  "vendor": "palo_alto",
  "device_type": "firewall",
  ...
}
```

### Update Device
```http
PUT /devices/:id
Content-Type: application/json
x-auth-token: jwt_token_here

{
  "hostname": "firewall-01-updated",
  "notes": "Updated perimeter firewall"
}
```

**Response:**
```json
{
  "id": "uuid",
  "hostname": "firewall-01-updated",
  ...
}
```

### Delete Device
```http
DELETE /devices/:id
x-auth-token: jwt_token_here
```

**Response:**
```json
{
  "msg": "Device removed successfully"
}
```

### Search Devices
```http
GET /devices/search/:term
x-auth-token: jwt_token_here
```

**Response:**
```json
[
  {
    "id": "uuid",
    "hostname": "core-switch-01",
    ...
  }
]
```

### Run Health Check on Device
```http
POST /devices/:id/health-check
x-auth-token: jwt_token_here
```

**Response:**
```json
{
  "ip_address": "192.168.1.1",
  "hostname": "core-switch-01",
  "timestamp": "2026-08-06T16:00:00.000Z",
  "ping": true,
  "ssh": true,
  "telnet": false,
  "snmp": true,
  "response_time_ms": 2,
  "metrics": {
    "device_id": "uuid",
    "timestamp": "2026-08-06T16:00:00.000Z",
    "cpu_utilization": 45.2,
    "memory_utilization": 62.8,
    "memory_total": 8388608,
    "memory_used": 5267456,
    "memory_free": 3121152,
    "interface_stats": [
      {
        "index": 1,
        "name": "GigabitEthernet1/0/1",
        "type": 6,
        "mtu": 1500,
        "speed": 1000000000,
        "phys_address": "00:1a:2b:3c:4d:5e",
        "admin_status": 1,
        "oper_status": 1,
        "in_octets": 1234567890,
        "out_octets": 9876543210,
        ...
      }
    ]
  }
}
```

### Discover Network
```http
POST /devices/discover
Content-Type: application/json
x-auth-token: jwt_token_here

{
  "network": "192.168.1.0/24",
  "snmp_communities": ["public", "private"],
  "timeout": 2000
}
```

**Response:**
```json
{
  "msg": "Discovery completed",
  "devices_found": 15,
  "devices": [
    {
      "id": "uuid",
      "hostname": "switch-01",
      "ip_address": "192.168.1.10",
      "vendor": "cisco",
      "device_type": "switch",
      ...
    }
  ]
}
```

### Execute Command on Device
```http
POST /devices/:id/execute-command
Content-Type: application/json
x-auth-token: jwt_token_here

{
  "command": "show version",
  "timeout": 30000
}
```

**Response:**
```json
{
  "command": "show version",
  "output": "Cisco IOS Software, C3750 Software (C3750-IPSERVICESK9-M), Version 15.0(2)SE4\n...\n",
  "success": true
}
```

### Get Device Configuration
```http
GET /devices/:id/config
x-auth-token: jwt_token_here
```

**Response:**
```json
{
  "device_id": "uuid",
  "hostname": "core-switch-01",
  "config": "version 15.0\n...\n",
  "timestamp": "2026-08-06T16:00:00.000Z"
}
```

## Error Responses

All endpoints may return error responses in the following format:

```json
{
  "msg": "Error description"
}
```

Common HTTP status codes:
- `200` - Success
- `201` - Created
- `400` - Bad Request
- `401` - Unauthorized
- `404` - Not Found
- `500` - Server Error

## Authentication

All endpoints (except `/auth/register` and `/auth/login`) require authentication. Include the JWT token in the `x-auth-token` header:

```http
x-auth-token: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

## Rate Limiting

Rate limiting is not currently implemented but is recommended for production deployments.

## WebSockets (Future)

Real-time updates will be available via WebSockets at `ws://localhost:3000/ws`.

Supported events:
- `device:status_change` - Device status changed
- `device:health_check` - Health check completed
- `monitoring:update` - New monitoring data available
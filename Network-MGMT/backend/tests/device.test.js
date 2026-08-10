const { expect } = require('chai');
const request = require('supertest');
const app = require('./server');
const { Device, User } = require('./models');

describe('Device API', function() {
  let authToken;
  let deviceId;

  before(async function() {
    // Create a test user and get auth token
    const user = await User.create({
      username: 'testuser',
      email: 'test@example.com',
      password_hash: '$2a$10$8CvjZVJyZpN6kzQeR0QOOOeS8tU6V7W8X9Y0Z1a2b3c4d5e6f7g8h',
      role: 'admin'
    });
    
    // In a real test, you'd get a JWT token here
    authToken = 'mock-token';
  });

  describe('GET /api/devices', function() {
    it('should return all devices', async function() {
      const res = await request(app)
        .get('/api/devices')
        .set('x-auth-token', authToken);
      
      expect(res).to.have.status(200);
      expect(res.body).to.be.an('array');
    });
  });

  describe('POST /api/devices', function() {
    it('should create a new device', async function() {
      const deviceData = {
        hostname: 'test-switch-01',
        ip_address: '192.168.1.100',
        vendor: 'cisco',
        device_type: 'switch',
        username: 'admin',
        password: 'password123',
        ssh_port: 22,
        snmp_community: 'public'
      };

      const res = await request(app)
        .post('/api/devices')
        .set('x-auth-token', authToken)
        .send(deviceData);
      
      expect(res).to.have.status(201);
      expect(res.body).to.have.property('id');
      expect(res.body.hostname).to.equal(deviceData.hostname);
      
      deviceId = res.body.id;
    });

    it('should fail without required fields', async function() {
      const res = await request(app)
        .post('/api/devices')
        .set('x-auth-token', authToken)
        .send({ hostname: 'test' });
      
      expect(res).to.have.status(400);
    });
  });

  describe('GET /api/devices/:id', function() {
    it('should return a specific device', async function() {
      const res = await request(app)
        .get(`/api/devices/${deviceId}`)
        .set('x-auth-token', authToken);
      
      expect(res).to.have.status(200);
      expect(res.body).to.have.property('id', deviceId);
    });

    it('should return 404 for non-existent device', async function() {
      const res = await request(app)
        .get('/api/devices/non-existent-id')
        .set('x-auth-token', authToken);
      
      expect(res).to.have.status(404);
    });
  });

  describe('PUT /api/devices/:id', function() {
    it('should update a device', async function() {
      const updateData = {
        hostname: 'updated-switch-01',
        notes: 'Updated notes'
      };

      const res = await request(app)
        .put(`/api/devices/${deviceId}`)
        .set('x-auth-token', authToken)
        .send(updateData);
      
      expect(res).to.have.status(200);
      expect(res.body.hostname).to.equal(updateData.hostname);
    });
  });

  describe('DELETE /api/devices/:id', function() {
    it('should delete a device', async function() {
      const res = await request(app)
        .delete(`/api/devices/${deviceId}`)
        .set('x-auth-token', authToken);
      
      expect(res).to.have.status(200);
      expect(res.body).to.have.property('msg', 'Device removed successfully');
    });
  });

  describe('POST /api/devices/:id/health-check', function() {
    it('should run health check on a device', async function() {
      // First create a device
      const device = await Device.create({
        hostname: 'health-check-test',
        ip_address: '192.168.1.200',
        vendor: 'cisco',
        device_type: 'switch',
        status: 'unknown'
      });

      const res = await request(app)
        .post(`/api/devices/${device.id}/health-check`)
        .set('x-auth-token', authToken);
      
      expect(res).to.have.status(200);
      expect(res.body).to.have.property('ping');
      expect(res.body).to.have.property('ssh');
      expect(res.body).to.have.property('snmp');
      
      // Clean up
      await device.destroy();
    });
  });
});

describe('Discovery Service', function() {
  this.timeout(10000);

  const { discoverNetwork } = require('./services/discovery');

  it('should discover devices on a network', async function() {
    // This is a basic test - in production, you'd test against a real network
    const devices = await discoverNetwork('192.168.1.0/24', {
      snmpCommunities: ['public'],
      timeout: 1000,
      saveToDatabase: false
    });

    expect(devices).to.be.an('array');
    // Note: This might return 0 devices if no devices are on the network
  });
});

describe('Monitoring Service', function() {
  const { monitorDevices } = require('./services/monitoring');

  it('should monitor multiple devices', async function() {
    // Create test devices
    const devices = [
      {
        id: 'test-device-1',
        hostname: 'test-device-1',
        ip_address: '192.168.1.201',
        vendor: 'cisco',
        device_type: 'switch'
      }
    ];

    const results = await monitorDevices(devices, { maxConcurrent: 5 });

    expect(results).to.be.an('array');
    expect(results[0]).to.have.property('ping');
    expect(results[0]).to.have.property('ssh');
    expect(results[0]).to.have.property('snmp');
  });
});
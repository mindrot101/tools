const ping = require('ping');
const { SSHManager } = require('../protocols/ssh');
const { TelnetManager } = require('../protocols/telnet');
const { SNMPManager } = require('../protocols/snmp');
const { Device } = require('../models');

/**
 * Monitoring Service
 * Performs health checks and collects metrics from network devices
 */
class MonitoringService {
  /**
   * Check device connectivity using multiple methods
   * @param {Object} device - Device object
   * @returns {Promise<Object>} Connectivity status
   */
  static async checkConnectivity(device) {
    const results = {
      ip_address: device.ip_address,
      hostname: device.hostname,
      timestamp: new Date().toISOString(),
      ping: false,
      ssh: false,
      telnet: false,
      snmp: false,
      response_time_ms: null
    };
    
    // Test ping
    try {
      const pingResult = await ping.promise.probe(device.ip_address, {
        timeout: 2000,
        min_reply: 1
      });
      results.ping = pingResult.alive;
      if (pingResult.alive) {
        results.response_time_ms = Math.round(pingResult.avg);
      }
    } catch (error) {
      console.error(`Ping failed for ${device.ip_address}:`, error.message);
    }
    
    // Test SSH
    try {
      const sshConn = await SSHManager.connect(device, { timeout: 5000 });
      results.ssh = true;
      SSHManager.disconnect(sshConn);
    } catch (error) {
      // SSH failure is common if not configured
    }
    
    // Test Telnet
    try {
      const telnetConn = await TelnetManager.connect(device, { timeout: 5000 });
      results.telnet = true;
      TelnetManager.disconnect(telnetConn);
    } catch (error) {
      // Telnet failure is common if not enabled
    }
    
    // Test SNMP
    try {
      const sysDescr = await SNMPManager.getSystemDescription(device);
      results.snmp = !!sysDescr && sysDescr !== 'Unknown';
    } catch (error) {
      // SNMP failure is common if not configured or wrong community
    }
    
    return results;
  }
  
  /**
   * Collect performance metrics from a device
   * @param {Object} device - Device object
   * @returns {Promise<Object>} Performance metrics
   */
  static async collectMetrics(device) {
    const metrics = {
      device_id: device.id,
      timestamp: new Date().toISOString(),
      cpu_utilization: null,
      memory_utilization: null,
      memory_total: null,
      memory_used: null,
      memory_free: null,
      interface_stats: []
    };
    
    try {
      // Try to get CPU utilization via SNMP
      const cpuUsage = await SNMPManager.getCPUUtilization(device);
      if (cpuUsage !== null) {
        metrics.cpu_utilization = parseFloat(cpuUsage);
      }
    } catch (error) {
      // CPU OID might not be supported
    }
    
    try {
      // Try to get memory utilization via SNMP
      const memInfo = await SNMPManager.getMemoryUtilization(device);
      if (memInfo.total > 0) {
        metrics.memory_total = memInfo.total;
        metrics.memory_used = memInfo.used;
        metrics.memory_free = memInfo.free;
        metrics.memory_utilization = memInfo.usagePercent;
      }
    } catch (error) {
      // Memory OID might not be supported
    }
    
    try {
      // Get interface statistics via SNMP
      const interfaces = await SNMPManager.getInterfaces(device);
      metrics.interface_stats = interfaces.map(iface => ({
        index: iface.index,
        name: iface['1.3.6.1.2.1.2.2.1.2'] || `Unknown-${iface.index}`, // ifDescr
        type: iface['1.3.6.1.2.1.2.2.1.3'] || 0, // ifType
        mtu: iface['1.3.6.1.2.1.2.2.1.4'] || 0, // ifMTU
        speed: iface['1.3.6.1.2.1.2.2.1.5'] || 0, // ifSpeed
        phys_address: iface['1.3.6.1.2.1.2.2.1.6'] || '', // ifPhysAddress
        admin_status: iface['1.3.6.1.2.1.2.2.1.7'] || 0, // ifAdminStatus
        oper_status: iface['1.3.6.1.2.1.2.2.1.8'] || 0, // ifOperStatus
        last_change: iface['1.3.6.1.2.1.2.2.1.9'] || 0, // ifLastChange
        in_octets: iface['1.3.6.1.2.1.2.2.1.10'] || 0, // ifInOctets
        in_ucast_pkts: iface['1.3.6.1.2.1.2.2.1.11'] || 0, // ifInUcastPkts
        in_nucast_pkts: iface['1.3.6.1.2.1.2.2.1.12'] || 0, // ifInNUcastPkts
        in_discards: iface['1.3.6.1.2.1.2.2.1.13'] || 0, // ifInDiscards
        in_errors: iface['1.3.6.1.2.1.2.2.1.14'] || 0, // ifInErrors
        in_unknown_protos: iface['1.3.6.1.2.1.2.2.1.15'] || 0, // ifInUnknownProtos
        out_octets: iface['1.3.6.1.2.1.2.2.1.16'] || 0, // ifOutOctets
        out_ucast_pkts: iface['1.3.6.1.2.1.2.2.1.17'] || 0, // ifOutUcastPkts
        out_nucast_pkts: iface['1.3.6.1.2.1.2.2.1.18'] || 0, // ifOutNUcastPkts
        out_discards: iface['1.3.6.1.2.1.2.2.1.19'] || 0, // ifOutDiscards
        out_errors: iface['1.3.6.1.2.1.2.2.1.20'] || 0 // ifOutErrors
      }));
    } catch (error) {
      console.warn(`Could not retrieve interface stats for ${device.ip_address}:`, error.message);
    }
    
    return metrics;
  }
  
  /**
   * Perform comprehensive device health check
   * @param {Object} device - Device object
   * @returns {Promise<Object>} Health check results
   */
  static async healthCheck(device) {
    try {
      // Run connectivity check
      const connectivity = await this.checkConnectivity(device);
      
      // If device is reachable via any method, collect metrics
      let metrics = null;
      if (connectivity.ping || connectivity.ssh || connectivity.telnet || connectivity.snmp) {
        try {
          metrics = await this.collectMetrics(device);
        } catch (error) {
          console.warn(`Could not collect metrics for ${device.ip_address}:`, error.message);
        }
      }
      
      return {
        ...connectivity,
        metrics: metrics
      };
    } catch (error) {
      console.error(`Health check failed for ${device.ip_address}:`, error);
      return {
        ip_address: device.ip_address,
        hostname: device.hostname,
        timestamp: new Date().toISOString(),
        ping: false,
        ssh: false,
        telnet: false,
        snmp: false,
        response_time_ms: null,
        error: error.message,
        metrics: null
      };
    }
  }
  
  /**
   * Monitor multiple devices concurrently
   * @param {Array} devices - Array of device objects
   * @param {Object} options - Monitoring options
   * @returns {Promise<Array>} Array of health check results
   */
  static async monitorDevices(devices, options = {}) {
    const {
      maxConcurrent = 10,
      includeMetrics = true
    } = options;
    
    console.log(`Starting health check for ${devices.length} devices...`);
    
    const results = [];
    
    // Process devices in batches to avoid overwhelming the network
    for (let i = 0; i < devices.length; i += maxConcurrent) {
      const batch = devices.slice(i, i + maxConcurrent);
      const batchPromises = batch.map(device => 
        this.healthCheck(device)
      );
      
      const batchResults = await Promise.allSettled(batchPromises);
      
      batchResults.forEach((result, index) => {
        if (result.status === 'fulfilled') {
          results.push(result.value);
        } else {
          console.error(`Health check failed for ${batch[index].ip_address}:`, result.reason);
          results.push({
            ip_address: batch[index].ip_address,
            hostname: batch[index].hostname,
            timestamp: new Date().toISOString(),
            ping: false,
            ssh: false,
            telnet: false,
            snmp: false,
            response_time_ms: null,
            error: result.reason.message,
            metrics: null
          });
        }
      });
    }
    
    console.log(`Health check complete. Processed ${results.length} devices.`);
    return results;
  }
}

module.exports = MonitoringService;
// Bound exports so destructured imports keep `this`
module.exports.monitorDevices = MonitoringService.monitorDevices.bind(MonitoringService);
module.exports.healthCheck = MonitoringService.healthCheck.bind(MonitoringService);

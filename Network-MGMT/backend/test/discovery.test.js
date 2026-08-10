const { expect } = require('chai');
const { cidrHosts } = require('../services/discovery');

describe('services/discovery cidrHosts', () => {
  it('/30 -> 2 usable hosts', () => expect(cidrHosts('10.0.0.0/30')).to.deep.equal(['10.0.0.1', '10.0.0.2']));
  it('/24 -> 254 hosts', () => expect(cidrHosts('192.168.1.0/24')).to.have.length(254));
  it('/32 -> single host', () => expect(cidrHosts('10.0.0.5/32')).to.deep.equal(['10.0.0.5']));
  it('throws on invalid CIDR', () => expect(() => cidrHosts('nope')).to.throw());
});

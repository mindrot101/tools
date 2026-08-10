const { expect } = require('chai');
const { encrypt, decrypt } = require('../utils/crypto');

describe('utils/crypto (AES-256-GCM)', () => {
  it('round-trips a secret', () => { const p = 'S3cret!pass'; expect(decrypt(encrypt(p))).to.equal(p); });
  it('handles empty string', () => { expect(decrypt(encrypt(''))).to.equal(''); });
  it('returns empty on malformed input', () => { expect(decrypt('not-a-token')).to.equal(''); });
  it('does not leak plaintext', () => { expect(encrypt('abc123')).to.not.contain('abc123'); });
  it('uses a random IV (different ciphertexts)', () => { expect(encrypt('same')).to.not.equal(encrypt('same')); });
});

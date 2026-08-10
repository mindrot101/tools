const { expect } = require('chai');
const { requireRole } = require('../middleware/auth');

describe('middleware/auth requireRole', () => {
  it('calls next() for a matching role', (done) => {
    requireRole('admin')({ user: { role: 'admin' } }, {}, () => done());
  });
  it('responds 403 for a non-matching role', () => {
    let code;
    const res = { status: (c) => { code = c; return { json: () => {} }; } };
    requireRole('admin')({ user: { role: 'viewer' } }, res, () => { throw new Error('next should not run'); });
    expect(code).to.equal(403);
  });
});

const jwt = require('jsonwebtoken');

function getSecret() {
  const s = process.env.JWT_SECRET;
  const weak = !s || s === 'your_jwt_secret' || /change_in_production/.test(s);
  if (weak && process.env.NODE_ENV === 'production') {
    throw new Error('JWT_SECRET must be set to a strong value in production');
  }
  return s || 'dev-insecure-secret';
}

const auth = (req, res, next) => {
  const header = req.header('x-auth-token') || '';
  const bearer = (req.headers.authorization || '').replace(/^Bearer\s+/i, '');
  const token = header || bearer;
  if (!token) return res.status(401).json({ msg: 'No token, authorization denied' });
  try {
    req.user = jwt.verify(token, getSecret()).user;
    next();
  } catch {
    res.status(401).json({ msg: 'Token is not valid' });
  }
};

const requireRole = (...roles) => (req, res, next) => {
  if (req.user && roles.includes(req.user.role)) return next();
  return res.status(403).json({ msg: `Access denied (requires role: ${roles.join(' or ')})` });
};

const admin = requireRole('admin');

module.exports = { auth, admin, requireRole, getSecret };

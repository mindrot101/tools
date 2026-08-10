const express = require('express');
const router = express.Router();
const bcrypt = require('bcryptjs');
const jwt = require('jsonwebtoken');
const rateLimit = require('express-rate-limit');
const { body, validationResult } = require('express-validator');
const { User } = require('../models');
const { auth, admin, requireRole, getSecret } = require('../middleware/auth');
const { audit } = require('../utils/audit');

const TOKEN_TTL = process.env.JWT_EXPIRES_IN || '8h';

const authLimiter = rateLimit({ windowMs: 15 * 60 * 1000, max: 20, standardHeaders: true, legacyHeaders: false });

const validate = (req, res, next) => {
  const errors = validationResult(req);
  if (!errors.isEmpty()) return res.status(400).json({ msg: 'Validation failed', errors: errors.array() });
  next();
};

function signToken(user) {
  const payload = { user: { id: user.id, username: user.username, role: user.role } };
  return jwt.sign(payload, getSecret(), { expiresIn: TOKEN_TTL });
}

// Register is ADMIN-ONLY (prevents privilege-escalation via self-registration).
router.post('/register', auth, admin,
  body('username').isString().trim().notEmpty(),
  body('email').isEmail(),
  body('password').isLength({ min: 8 }),
  body('role').optional().isIn(['admin', 'operator', 'viewer']),
  validate,
  async (req, res) => {
    try {
      const { username, email, password, role } = req.body;
      if (await User.findOne({ where: { username } })) return res.status(400).json({ msg: 'Username already exists' });
      if (await User.findOne({ where: { email } })) return res.status(400).json({ msg: 'Email already exists' });
      const password_hash = await bcrypt.hash(password, 10);
      const user = await User.create({ username, email, password_hash, role: role || 'viewer' });
      await audit(req, 'user.create', username, `role=${user.role}`);
      res.status(201).json({ id: user.id, username: user.username, role: user.role });
    } catch (err) {
      res.status(500).json({ msg: 'Server error' });
    }
  }
);

router.post('/login', authLimiter,
  body('username').isString().trim().notEmpty(),
  body('password').isString().notEmpty(),
  validate,
  async (req, res) => {
    try {
      const { username, password } = req.body;
      const user = await User.findOne({ where: { username } });
      if (!user || !user.is_active) return res.status(400).json({ msg: 'Invalid credentials' });
      const ok = await bcrypt.compare(password, user.password_hash);
      if (!ok) return res.status(400).json({ msg: 'Invalid credentials' });
      res.json({ token: signToken(user), user: { id: user.id, username: user.username, role: user.role } });
    } catch (err) {
      res.status(500).json({ msg: 'Server error' });
    }
  }
);

router.get('/me', auth, async (req, res) => {
  try {
    const user = await User.findByPk(req.user.id);
    if (!user) return res.status(404).json({ msg: 'User not found' });
    res.json({ id: user.id, username: user.username, email: user.email, role: user.role });
  } catch {
    res.status(500).json({ msg: 'Server error' });
  }
});

// Change own password
router.post('/change-password', auth,
  body('current_password').isString().notEmpty(),
  body('new_password').isLength({ min: 8 }),
  validate,
  async (req, res) => {
    try {
      const user = await User.findByPk(req.user.id);
      if (!user || !(await bcrypt.compare(req.body.current_password, user.password_hash))) {
        return res.status(400).json({ msg: 'Current password is incorrect' });
      }
      user.password_hash = await bcrypt.hash(req.body.new_password, 10);
      await user.save();
      await audit(req, 'user.change_password', user.username);
      res.json({ msg: 'Password updated' });
    } catch {
      res.status(500).json({ msg: 'Server error' });
    }
  }
);

module.exports = router;

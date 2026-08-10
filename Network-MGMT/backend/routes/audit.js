const express = require('express');
const router = express.Router();
const { AuditLog } = require('../models');
const { auth, requireRole } = require('../middleware/auth');

router.get('/', auth, requireRole('admin'), async (req, res) => {
  try {
    const limit = Math.min(500, Math.max(1, parseInt(req.query.limit) || 100));
    const logs = await AuditLog.findAll({ order: [['createdAt', 'DESC']], limit });
    res.json(logs);
  } catch { res.status(500).json({ msg: 'Server error' }); }
});

module.exports = router;

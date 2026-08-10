module.exports = {
  async up({ context: qi }) {
    try { await qi.addIndex('audit_logs', ['createdAt'], { name: 'audit_logs_created_at_idx' }); } catch (e) {}
  },
  async down({ context: qi }) {
    try { await qi.removeIndex('audit_logs', 'audit_logs_created_at_idx'); } catch (e) {}
  }
};

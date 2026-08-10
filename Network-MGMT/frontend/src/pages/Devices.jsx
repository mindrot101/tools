import { useState, useEffect } from 'react';
import {
  Box, Typography, Button, Stack, Alert, CircularProgress, Chip, TextField, MenuItem, IconButton, Pagination, Divider,
  Table, TableHead, TableRow, TableCell, TableBody, TableContainer, Paper, Dialog, DialogTitle, DialogContent, DialogActions
} from '@mui/material';
import { Delete as DeleteIcon, Refresh as RefreshIcon, Add as AddIcon, History as HistoryIcon } from '@mui/icons-material';
import api from '../services/api';
import { useAuth } from '../context/AuthContext';

const VENDORS = ['cisco', 'palo_alto', 'aruba', 'arista', 'juniper', 'other'];
const TYPES = ['router', 'switch', 'firewall', 'load_balancer', 'other'];
const EMPTY = {
  hostname: '', ip_address: '', vendor: 'cisco', device_type: 'switch', username: '', password: '',
  ssh_port: 22, snmp_version: '2c', snmp_community: 'public',
  snmp_user: '', snmp_security_level: 'authPriv', snmp_auth_protocol: 'sha', snmp_auth_key: '', snmp_priv_protocol: 'aes', snmp_priv_key: '',
  notes: ''
};
const statusColor = (s) => ({ online: 'success', offline: 'error', maintenance: 'warning' }[s] || 'default');

export default function Devices() {
  const { user } = useAuth();
  const isAdmin = user?.role === 'admin';
  const [devices, setDevices] = useState([]);
  const [meta, setMeta] = useState({ total: 0, page: 1, pages: 1 });
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [open, setOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState(EMPTY);
  const [backups, setBackups] = useState(null);

  const load = async (p = page, q = search) => {
    setLoading(true);
    try {
      const r = await api.get('/devices', { params: { page: p, limit: 10, search: q || undefined } });
      setDevices(r.data.data); setMeta({ total: r.data.total, page: r.data.page, pages: r.data.pages }); setError('');
    } catch (e) { setError(e.response?.data?.msg || 'Failed to load devices'); }
    finally { setLoading(false); }
  };
  useEffect(() => { load(1, ''); }, []);

  const change = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));
  const valid = form.hostname.trim() && form.ip_address.trim() && form.username.trim();

  const submit = async () => {
    setSaving(true); setError('');
    try { await api.post('/devices', form); setOpen(false); setForm(EMPTY); await load(1, search); setPage(1); }
    catch (e) { setError(e.response?.data?.msg || 'Failed to add device'); }
    finally { setSaving(false); }
  };
  const remove = async (id) => { try { await api.delete(`/devices/${id}`); await load(); } catch (e) { setError(e.response?.data?.msg || 'Failed to delete'); } };
  const showBackups = async (d) => {
    try { const r = await api.get(`/devices/${d.id}/backups`); setBackups({ device: d, list: r.data }); }
    catch (e) { setError(e.response?.data?.msg || 'Failed to load backups'); }
  };

  return (
    <Box>
      <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 2 }}>
        <Typography variant="h4">Devices</Typography>
        <Stack direction="row" spacing={1}>
          <Button startIcon={<RefreshIcon />} onClick={() => load()}>Refresh</Button>
          <Button variant="contained" startIcon={<AddIcon />} onClick={() => setOpen(true)}>Add Device</Button>
        </Stack>
      </Stack>

      <Stack direction="row" spacing={1} sx={{ mb: 2 }}>
        <TextField size="small" label="Search" value={search} onChange={(e) => setSearch(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && (setPage(1), load(1, search))} />
        <Button onClick={() => { setPage(1); load(1, search); }}>Go</Button>
      </Stack>

      {error && <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError('')}>{error}</Alert>}

      {loading ? <Box sx={{ textAlign: 'center', py: 6 }}><CircularProgress /></Box> : (
        <>
          <TableContainer component={Paper}>
            <Table size="small">
              <TableHead><TableRow>
                <TableCell>Hostname</TableCell><TableCell>IP</TableCell><TableCell>Vendor</TableCell><TableCell>Type</TableCell>
                <TableCell>SNMP</TableCell><TableCell>Status</TableCell><TableCell align="right">Actions</TableCell>
              </TableRow></TableHead>
              <TableBody>
                {devices.map((d) => (
                  <TableRow key={d.id} hover>
                    <TableCell>{d.hostname}</TableCell><TableCell>{d.ip_address}</TableCell>
                    <TableCell>{d.vendor}</TableCell><TableCell>{d.device_type}</TableCell>
                    <TableCell>v{d.snmp_version}</TableCell>
                    <TableCell><Chip size="small" label={d.status} color={statusColor(d.status)} /></TableCell>
                    <TableCell align="right">
                      <IconButton size="small" title="Config backups" onClick={() => showBackups(d)}><HistoryIcon fontSize="small" /></IconButton>
                      {isAdmin && <IconButton size="small" color="error" onClick={() => remove(d.id)}><DeleteIcon fontSize="small" /></IconButton>}
                    </TableCell>
                  </TableRow>
                ))}
                {devices.length === 0 && <TableRow><TableCell colSpan={7} align="center">No devices.</TableCell></TableRow>}
              </TableBody>
            </Table>
          </TableContainer>
          <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mt: 2 }}>
            <Typography variant="body2" color="text.secondary">{meta.total} device(s)</Typography>
            <Pagination count={meta.pages} page={page} onChange={(e, p) => { setPage(p); load(p, search); }} />
          </Stack>
        </>
      )}

      <Dialog open={open} onClose={() => setOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle>Add Device</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField label="Hostname" required value={form.hostname} onChange={change('hostname')} fullWidth />
            <TextField label="IP Address" required value={form.ip_address} onChange={change('ip_address')} fullWidth />
            <Stack direction="row" spacing={2}>
              <TextField label="Vendor" select value={form.vendor} onChange={change('vendor')} fullWidth>{VENDORS.map((v) => <MenuItem key={v} value={v}>{v}</MenuItem>)}</TextField>
              <TextField label="Type" select value={form.device_type} onChange={change('device_type')} fullWidth>{TYPES.map((t) => <MenuItem key={t} value={t}>{t}</MenuItem>)}</TextField>
            </Stack>
            <Stack direction="row" spacing={2}>
              <TextField label="Username" required value={form.username} onChange={change('username')} fullWidth />
              <TextField label="Password" type="password" value={form.password} onChange={change('password')} fullWidth />
            </Stack>
            <Divider>SNMP</Divider>
            <Stack direction="row" spacing={2}>
              <TextField label="SNMP Version" select value={form.snmp_version} onChange={change('snmp_version')} sx={{ width: 160 }}>
                {['1', '2c', '3'].map((v) => <MenuItem key={v} value={v}>{v}</MenuItem>)}
              </TextField>
              {form.snmp_version !== '3'
                ? <TextField label="Community" value={form.snmp_community} onChange={change('snmp_community')} fullWidth />
                : <TextField label="SNMPv3 User" value={form.snmp_user} onChange={change('snmp_user')} fullWidth />}
            </Stack>
            {form.snmp_version === '3' && (
              <>
                <Stack direction="row" spacing={2}>
                  <TextField label="Security Level" select value={form.snmp_security_level} onChange={change('snmp_security_level')} fullWidth>
                    {['noAuthNoPriv', 'authNoPriv', 'authPriv'].map((v) => <MenuItem key={v} value={v}>{v}</MenuItem>)}
                  </TextField>
                </Stack>
                <Stack direction="row" spacing={2}>
                  <TextField label="Auth Proto" select value={form.snmp_auth_protocol} onChange={change('snmp_auth_protocol')} sx={{ width: 140 }}>
                    {['md5', 'sha'].map((v) => <MenuItem key={v} value={v}>{v}</MenuItem>)}
                  </TextField>
                  <TextField label="Auth Key" type="password" value={form.snmp_auth_key} onChange={change('snmp_auth_key')} fullWidth />
                </Stack>
                <Stack direction="row" spacing={2}>
                  <TextField label="Priv Proto" select value={form.snmp_priv_protocol} onChange={change('snmp_priv_protocol')} sx={{ width: 140 }}>
                    {['des', 'aes'].map((v) => <MenuItem key={v} value={v}>{v}</MenuItem>)}
                  </TextField>
                  <TextField label="Priv Key" type="password" value={form.snmp_priv_key} onChange={change('snmp_priv_key')} fullWidth />
                </Stack>
              </>
            )}
            <TextField label="Notes" value={form.notes} onChange={change('notes')} fullWidth multiline minRows={2} />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpen(false)}>Cancel</Button>
          <Button variant="contained" disabled={!valid || saving} onClick={submit}>{saving ? 'Saving…' : 'Add Device'}</Button>
        </DialogActions>
      </Dialog>

      <Dialog open={!!backups} onClose={() => setBackups(null)} fullWidth maxWidth="sm">
        <DialogTitle>Config Backups — {backups?.device?.hostname}</DialogTitle>
        <DialogContent>
          {backups?.list?.length ? (
            <Table size="small"><TableHead><TableRow><TableCell>When</TableCell><TableCell>Hash</TableCell></TableRow></TableHead>
              <TableBody>{backups.list.map((b) => (
                <TableRow key={b.id}><TableCell>{new Date(b.createdAt).toLocaleString()}</TableCell><TableCell>{b.hash?.slice(0, 16)}…</TableCell></TableRow>
              ))}</TableBody></Table>
          ) : <Typography color="text.secondary" sx={{ mt: 1 }}>No backups yet. Admins can pull one via GET /devices/:id/config.</Typography>}
        </DialogContent>
        <DialogActions><Button onClick={() => setBackups(null)}>Close</Button></DialogActions>
      </Dialog>
    </Box>
  );
}

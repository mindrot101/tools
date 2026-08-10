import { useState } from 'react';
import { AppBar, Toolbar, Typography, Button, Box, Chip, Dialog, DialogTitle, DialogContent, DialogActions, TextField, Alert, Stack } from '@mui/material';
import { useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import api from '../services/api';

const links = [
  { label: 'Dashboard', path: '/' },
  { label: 'Devices', path: '/devices' },
  { label: 'Monitoring', path: '/monitoring' },
  { label: 'Discovery', path: '/discovery' },
  { label: 'Alerts', path: '/alerts' }
];

export default function NavBar() {
  const nav = useNavigate();
  const loc = useLocation();
  const { user, logout } = useAuth();
  const [open, setOpen] = useState(false);
  const [cur, setCur] = useState('');
  const [next, setNext] = useState('');
  const [msg, setMsg] = useState(null);

  const change = async () => {
    setMsg(null);
    try {
      await api.post('/auth/change-password', { current_password: cur, new_password: next });
      setMsg({ t: 'success', m: 'Password changed.' }); setCur(''); setNext('');
    } catch (e) { setMsg({ t: 'error', m: e.response?.data?.msg || 'Failed (min 8 chars)' }); }
  };

  return (
    <AppBar position="static" sx={{ mb: 3 }}>
      <Toolbar>
        <Typography variant="h6" sx={{ mr: 4 }}>NetMgmt</Typography>
        <Box sx={{ flexGrow: 1, display: 'flex', gap: 1 }}>
          {links.map((l) => (
            <Button key={l.path} color="inherit" variant={loc.pathname === l.path ? 'outlined' : 'text'} onClick={() => nav(l.path)}>{l.label}</Button>
          ))}
        </Box>
        {user && <Chip size="small" label={`${user.username} · ${user.role}`} sx={{ mr: 2, bgcolor: 'rgba(255,255,255,0.18)', color: '#fff' }} />}
        <Button color="inherit" onClick={() => setOpen(true)}>Password</Button>
        <Button color="inherit" onClick={() => { logout(); nav('/login'); }}>Logout</Button>
      </Toolbar>

      <Dialog open={open} onClose={() => setOpen(false)}>
        <DialogTitle>Change Password</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1, width: 320 }}>
            {msg && <Alert severity={msg.t}>{msg.m}</Alert>}
            <TextField label="Current password" type="password" value={cur} onChange={(e) => setCur(e.target.value)} />
            <TextField label="New password (min 8)" type="password" value={next} onChange={(e) => setNext(e.target.value)} />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpen(false)}>Close</Button>
          <Button variant="contained" disabled={!cur || next.length < 8} onClick={change}>Update</Button>
        </DialogActions>
      </Dialog>
    </AppBar>
  );
}

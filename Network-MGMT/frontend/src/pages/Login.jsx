import { useState } from 'react';
import { Button, TextField, Typography, Box, Container } from '@mui/material';
import { useAuth } from '../context/AuthContext';
import { useNavigate } from 'react-router-dom';

const Login = () => {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError('');
    try {
      await login(username.trim(), password);
      navigate('/');
    } catch (err) {
      setError(err.response?.data?.msg || 'Login failed. Check your credentials.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <Container maxWidth="xs" sx={{ mt: 8 }}>
      <Box sx={{ textAlign: 'center', mb: 2 }}>
        <Typography variant="h4" gutterBottom>Network Management Platform</Typography>
        <Typography variant="h6" color="text.secondary">Sign in to your account</Typography>
      </Box>
      <Box component="form" onSubmit={handleSubmit}>
        <TextField margin="normal" required fullWidth label="Username" autoFocus
          value={username} onChange={(e) => setUsername(e.target.value)} />
        <TextField margin="normal" required fullWidth label="Password" type="password"
          value={password} onChange={(e) => setPassword(e.target.value)} />
        <Button type="submit" fullWidth variant="contained" sx={{ mt: 3, mb: 2 }} disabled={loading}>
          {loading ? 'Signing in...' : 'Sign In'}
        </Button>
        {error && <Typography color="error" sx={{ mb: 2 }}>{error}</Typography>}
      </Box>
      <Box sx={{ textAlign: 'center' }}>
        <Typography variant="body2" color="text.secondary">Default credentials: admin / admin</Typography>
      </Box>
    </Container>
  );
};

export default Login;

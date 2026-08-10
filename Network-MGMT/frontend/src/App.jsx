import { Routes, Route, Navigate } from 'react-router-dom';
import { CssBaseline, Container, Box } from '@mui/material';
import NavBar from './components/NavBar';
import Dashboard from './pages/Dashboard';
import Devices from './pages/Devices';
import Monitoring from './pages/Monitoring';
import Discovery from './pages/Discovery';
import Alerts from './pages/Alerts';
import Login from './pages/Login';
import { useAuth } from './context/AuthContext';

function App() {
  const { user, loading } = useAuth();
  if (loading) return <Box sx={{ p: 3 }}>Loading...</Box>;

  if (!user) {
    return (
      <>
        <CssBaseline />
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="*" element={<Navigate to="/login" replace />} />
        </Routes>
      </>
    );
  }

  return (
    <>
      <CssBaseline />
      <NavBar />
      <Container maxWidth="lg" sx={{ pb: 6 }}>
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/devices" element={<Devices />} />
          <Route path="/monitoring" element={<Monitoring />} />
          <Route path="/discovery" element={<Discovery />} />
          <Route path="/alerts" element={<Alerts />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </Container>
    </>
  );
}

export default App;

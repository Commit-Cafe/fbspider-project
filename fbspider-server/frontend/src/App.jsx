import { Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider, useAuth } from './auth';
import Layout from './components/Layout';
import Login from './pages/Login';
import Dashboard from './pages/Dashboard';
import BMManagement from './pages/BMManagement';
import PixelManagement from './pages/PixelManagement';
import AdLibrary from './pages/AdLibrary';
import CampaignManagement from './pages/CampaignManagement';
import Settings from './pages/Settings';
import Users from './pages/Users';
import DeviceControl from './pages/DeviceControl';
import ApiKeys from './pages/ApiKeys';
import CreateAd from './pages/CreateAd';

function ProtectedRoute({ children, managerOnly = false }) {
  const { user } = useAuth();
  if (!user) return <Navigate to="/login" replace />;
  if (managerOnly && !['admin', 'leader'].includes(user.role)) return <Navigate to="/dashboard" replace />;
  return children;
}

export default function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/" element={<ProtectedRoute><Layout /></ProtectedRoute>}>
          <Route index element={<Navigate to="/dashboard" replace />} />
          <Route path="dashboard" element={<Dashboard />} />
          <Route path="bm" element={<BMManagement />} />
          <Route path="pixels" element={<PixelManagement />} />
          <Route path="campaigns" element={<CampaignManagement />} />
          <Route path="ad-library" element={<AdLibrary />} />
          <Route path="create-ad" element={<CreateAd />} />
          <Route path="settings" element={<Settings />} />
          <Route path="users" element={<ProtectedRoute managerOnly><Users /></ProtectedRoute>} />
          <Route path="device-control" element={<ProtectedRoute managerOnly><DeviceControl /></ProtectedRoute>} />
          <Route path="api-keys" element={<ProtectedRoute managerOnly><ApiKeys /></ProtectedRoute>} />
        </Route>
        <Route path="*" element={<Navigate to="/dashboard" replace />} />
      </Routes>
    </AuthProvider>
  );
}

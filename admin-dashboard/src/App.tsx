import { Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider } from './contexts/AuthContext';
import ProtectedRoute from './components/ProtectedRoute';
import Layout from './components/Layout';
import Login from './pages/Login';
import Dashboard from './pages/Dashboard';
import Agents from './pages/Agents';
import Memory from './pages/Memory';
import Teams from './pages/Teams';
import Federation from './pages/Federation';
import AuditLogs from './pages/AuditLogs';
import Settings from './pages/Settings';

function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route
          path="/"
          element={
            <ProtectedRoute>
              <Layout />
            </ProtectedRoute>
          }
        >
          <Route index element={<Navigate to="/dashboard" replace />} />
          <Route path="dashboard" element={<Dashboard />} />
          <Route path="agents" element={<Agents />} />
          <Route path="memory" element={<Memory />} />
          <Route path="teams" element={<Teams />} />
          <Route path="federation" element={<Federation />} />
          <Route path="audit" element={<AuditLogs />} />
          <Route path="settings" element={<Settings />} />
        </Route>
      </Routes>
    </AuthProvider>
  );
}

export default App;

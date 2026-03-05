import { Routes, Route, Navigate } from 'react-router-dom'
import { AuthProvider } from './contexts/AuthContext'
import Layout from './components/Layout'
import ProtectedRoute from './components/ProtectedRoute'
import Login from './pages/Login'
import Signup from './pages/Signup'
import ForgotPassword from './pages/ForgotPassword'
import ResetPassword from './pages/ResetPassword'
import Dashboard from './pages/Dashboard'
import Agents from './pages/Agents'
import Integrations from './pages/Integrations'
import Memory from './pages/Memory'
import Settings from './pages/Settings'
import GettingStarted from './pages/GettingStarted'
import Billing from './pages/Billing'
import Credits from './pages/Credits'
import Earnings from './pages/Earnings'
import ApiAccess from './pages/ApiAccess'

export default function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/signup" element={<Signup />} />
        <Route path="/forgot-password" element={<ForgotPassword />} />
        <Route path="/reset-password" element={<ResetPassword />} />
        <Route path="/" element={<ProtectedRoute><Layout /></ProtectedRoute>}>
          <Route index element={<Dashboard />} />
          <Route path="getting-started" element={<GettingStarted />} />
          <Route path="agents" element={<Agents />} />
          <Route path="integrations" element={<Integrations />} />
          <Route path="memory" element={<Memory />} />
          <Route path="billing" element={<Billing />} />
          <Route path="credits" element={<Credits />} />
          <Route path="earnings" element={<Earnings />} />
          <Route path="api" element={<ApiAccess />} />
          <Route path="settings" element={<Settings />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </AuthProvider>
  )
}

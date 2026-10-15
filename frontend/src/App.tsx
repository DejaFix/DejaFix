import type { ReactNode } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import { Layout } from './components/Layout'
import Admin from './pages/Admin'
import Alerts from './pages/Alerts'
import Cost from './pages/Cost'
import Dashboard from './pages/Dashboard'
import IncidentDetail from './pages/IncidentDetail'
import Login from './pages/Login'
import PlanDetail from './pages/PlanDetail'
import Plans from './pages/Plans'
import Reports from './pages/Reports'
import ServerCompare from './pages/ServerCompare'
import { useAuth } from './state/auth'

function RequireAuth({ children }: { children: ReactNode }) {
  const { user } = useAuth()
  return user ? <>{children}</> : <Navigate to="/login" replace />
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route element={<RequireAuth><Layout /></RequireAuth>}>
        <Route index element={<Dashboard />} />
        <Route path="incidents/:id" element={<IncidentDetail />} />
        <Route path="plans" element={<Plans />} />
        <Route path="plans/:id" element={<PlanDetail />} />
        <Route path="reports" element={<Reports />} />
        <Route path="cost" element={<Cost />} />
        <Route path="compare" element={<ServerCompare />} />
        <Route path="alerts" element={<Alerts />} />
        <Route path="admin" element={<Admin />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}

import type { ReactNode } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import { Layout } from './components/Layout'
import Admin from './pages/Admin'
import Alerts from './pages/Alerts'
import ComingSoon from './pages/ComingSoon'
import Dashboard from './pages/Dashboard'
import IncidentSummary from './pages/IncidentSummary'
import Login from './pages/Login'
import PlanDetail from './pages/PlanDetail'
import Plans from './pages/Plans'
import Reports from './pages/Reports'
import { useAuth } from './state/auth'

function RequireAuth({ children }: { children: ReactNode }) {
  const { status } = useAuth()
  if (status === 'restoring') return null
  return status === 'authenticated' ? <>{children}</> : <Navigate to="/login" replace />
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route
        element={
          <RequireAuth>
            <Layout />
          </RequireAuth>
        }
      >
        <Route index element={<Dashboard />} />
        <Route path="incidents/:id" element={<IncidentSummary />} />
        <Route path="plans" element={<Plans />} />
        <Route path="plans/:id" element={<PlanDetail />} />
        <Route path="reports" element={<Reports />} />
        <Route path="cost" element={<ComingSoon title="비용 절감" />} />
        <Route path="compare" element={<ComingSoon title="서버 비교" />} />
        <Route path="alerts" element={<Alerts />} />
        <Route path="admin" element={<Admin />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}

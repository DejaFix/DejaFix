import type { ReactNode } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import { Layout } from './components/Layout'
import Dashboard from './pages/Dashboard'
import IncidentDetail from './pages/IncidentDetail'
import Login from './pages/Login'
import Placeholder from './pages/Placeholder'
import PlanDetail from './pages/PlanDetail'
import Plans from './pages/Plans'
import Reports from './pages/Reports'
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
        <Route path="cost" element={<Placeholder title="비용 절감" icon="cost" description="AWS MCP 연동 후 인스턴스 적정 크기 권고와 절감 추정을 보여 줍니다." />} />
        <Route path="compare" element={<Placeholder title="서버 비교" icon="compare" description="같은 알림이 난 서버들의 지표를 나란히 비교하는 화면입니다." />} />
        <Route path="alerts" element={<Placeholder title="알림" icon="bell" description="알림 설정과 메일 발송 결과를 확인하는 화면입니다." />} />
        <Route path="admin" element={<Placeholder title="관리자" icon="admin" description="사용자와 권한을 관리하는 화면입니다." />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}

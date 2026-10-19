import { Link, useParams } from 'react-router-dom'
import { FocusCard } from '../components/FocusCard'
import IncidentDetail from './IncidentDetail'
import { ApiError } from '../lib/http'
import { useIncidentDetail } from '../lib/queries'

/** 현황에서 장애를 누르면 열리는 화면: 위에 ① 무엇이 · ② 왜 · ③ 어떻게 요약 카드, 그 아래에 장애 상세 내용. */
export default function IncidentSummary() {
  const { id = '' } = useParams()
  const { data: res, isLoading, isError, error, dataUpdatedAt } = useIncidentDetail(id)
  const incident = res?.data.incident

  if (isLoading)
    return (
      <div className="page">
        <div className="skeleton" />
      </div>
    )
  if (!incident) {
    const notFound = error instanceof ApiError && error.status === 404
    return (
      <div className="page">
        <div className="empty">
          <h2>{isError && !notFound ? '장애 정보를 불러오지 못했습니다' : '장애를 찾을 수 없습니다'}</h2>
          <Link className="btn" to="/">
            현황으로 돌아가기
          </Link>
        </div>
      </div>
    )
  }
  return (
    <div className="page">
      <div className="crumb">
        <Link to="/">현황 · 장애 대응</Link> / 장애 요약
      </div>
      <div className="page-head">
        <h1 className="page-title">지금 확인할 장애</h1>
        <p className="page-sub">무엇이 → 왜 → 어떻게</p>
      </div>
      {isError && <p className="card-sub">갱신 실패 — 마지막으로 받은 내용을 표시 중입니다.</p>}
      <FocusCard incident={incident} nowMs={dataUpdatedAt} />
      <IncidentDetail embedded />
    </div>
  )
}
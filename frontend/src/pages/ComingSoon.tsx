// 비용 절감·서버 비교는 L1(AWS 연동) 범위. 목 데이터 화면을 열지 않고 안내만 보여 준다(FR-FE-013, API 호출 없음).
export default function ComingSoon({ title }: { title: string }) {
  return (
    <div className="page">
      <div className="page-head">
        <h1 className="page-title">{title}</h1>
      </div>
      <div className="note" role="status">
        준비 중입니다. L1에서 제공 예정입니다.
      </div>
    </div>
  )
}

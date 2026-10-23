# frontend

React + Vite 웹 UI

## 실행
cd frontend
npm install
npm run dev

http://localhost:5173 에서 확인합니다. 로그인은 목업이라 아무 아이디와 비밀번호로 들어갈 수 있습니다.

## 빌드
npm run build

데이터는 목업(src/lib/mock.ts)입니다. 백엔드가 준비되면 src/lib/api.ts만 교체합니다.
## 총괄 에이전트 화면 (관리자 > 총괄 에이전트)
관리자 계정으로 로그인하면 사이드바 `관리자` 아래에 `총괄 에이전트`가 보입니다(`/admin/orchestrator`).
DejaFix 장애 대응에서 부서 에이전트들이 한 일(사건 흐름·부서별 사용량)을 읽기 전용으로 보여 줍니다. 승인·실행 버튼은 없습니다.
- 화면은 `common-frontend`(`@dejafix/common-frontend`)의 Card·StatCard·DataTable·Chip·PageHeader·Notice·EChart를 씁니다.
- 데이터는 Backend `GET /api/orchestrator/incidents`·`/departments`(`contracts/api.md` 6장). 백엔드 `.env`의 `ORCHESTRATOR_URL`에 총괄 주소를 적습니다.
- 백엔드 없이 개발하면 MSW가 실제 총괄 응답을 담은 샘플(`src/mocks/orchestratorSample.ts`)로 답합니다. `?scenario=orchestrator_down`을 붙이면 총괄이 없을 때의 화면을 볼 수 있습니다.
- 실제 총괄과 같이 보려면 `frontend/.env.local`에 `VITE_MSW_PASSTHROUGH=orchestrator`(로그인도 자동으로 통과)를 두고 백엔드·총괄을 띄웁니다.

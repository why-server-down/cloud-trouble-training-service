import { StrictMode } from 'react'
import ReactDOM from 'react-dom/client'
import '@fontsource/ibm-plex-sans-kr/400.css'
import '@fontsource/ibm-plex-sans-kr/700.css'
import App from './App'
import './index.css'

/*
 * StrictMode 는 개발 모드에서 effect 를 두 번 실행한다 (FE-16/17).
 *
 * 켜는 이유: "중복 interval·중복 WebSocket·중복 세션이 남지 않는다"는 인수 조건을
 * 검증할 수단이 없었다. 폴링(usePolling)과 세션 생성(useEnvironmentSessions)은
 * 각각 자기 타이머 정리와 in-flight 가드를 갖고 있어 이중 실행에 안전하다.
 * 프로덕션 빌드에서는 한 번만 실행된다.
 */
ReactDOM.createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)

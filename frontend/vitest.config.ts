import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

// vitest 는 이 파일이 있으면 vite.config.ts 를 읽지 않는다. dev server 설정(proxy 등)은
// 테스트에 필요 없지만, 앞으로 컴포넌트(.tsx) 테스트를 붙일 때 JSX 변환이 필요하므로
// react 플러그인만 가져온다.
export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    include: ['src/**/*.test.{ts,tsx}'],
    // globals 를 켜지 않는다 — 테스트 파일이 vitest 에서 명시적으로 import 하면
    // tsconfig 에 별도 types 설정 없이 `tsc` 타입 체크가 그대로 통과한다.
    globals: false,
    restoreMocks: true,
    unstubGlobals: true,
  },
})

/**
 * ESLint 8 (eslintrc) 설정.
 *
 * 현재 package.json 에 이미 설치된 플러그인만 사용한다. flat config(eslint.config.js)는
 * ESLint 9 부터가 기본이고, 여기 플러그인들은 아직 eslintrc 조합으로 검증된 버전이라
 * 업그레이드는 별도 작업으로 분리한다.
 */
module.exports = {
  root: true,
  env: { browser: true, es2020: true, node: true },
  extends: ['eslint:recommended', 'plugin:@typescript-eslint/recommended'],
  parser: '@typescript-eslint/parser',
  parserOptions: { ecmaVersion: 'latest', sourceType: 'module' },
  plugins: ['@typescript-eslint', 'react-hooks', 'react-refresh'],
  ignorePatterns: ['dist', 'node_modules', 'src/vite-env.d.ts'],
  rules: {
    // `let timer; ... timer = setInterval(...)` 처럼 선언과 대입 사이에서 클로저가
    // 값을 읽는 패턴을 const 로 바꿀 수는 없다. ESLint 가 문서에서 안내하는 예외다.
    'prefer-const': ['error', { ignoreReadBeforeAssign: true }],
    'react-hooks/rules-of-hooks': 'error',
    'react-hooks/exhaustive-deps': 'error',
    'react-refresh/only-export-components': ['error', { allowConstantExport: true }],
  },
}

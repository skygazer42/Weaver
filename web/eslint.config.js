// ESLint v9+ uses flat config by default.
// Next.js provides a flat config export via eslint-config-next.
module.exports = [
  {
    ignores: [
      '.next/**',
      '.next-e2e/**',
      'node_modules/**',
    ],
  },
  ...require('eslint-config-next/core-web-vitals'),
  {
    rules: {
      // This rule flags common, valid React patterns (e.g. syncing state with
      // external systems like localStorage, Web Workers, etc.).
      'react-hooks/set-state-in-effect': 'off',
    },
  },
]

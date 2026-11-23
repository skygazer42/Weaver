import next from 'eslint-config-next'

const config = [
  ...next,
  {
    rules: {
      '@next/next/no-img-element': 'off',
      '@typescript-eslint/ban-ts-comment': 'off',
      '@typescript-eslint/no-empty-object-type': 'off',
      '@typescript-eslint/no-explicit-any': 'off',
      '@typescript-eslint/no-unused-vars': 'off',
      'prefer-const': 'off',
      'react/no-unescaped-entities': 'off',
    },
  },
  {
    files: ['components/**/*.{ts,tsx}', 'hooks/**/*.ts', 'lib/i18n/**/*.tsx'],
    // shortcut: keep React Compiler findings visible as warnings until these components and hooks are migrated.
    rules: {
      'react-hooks/immutability': 'warn',
      'react-hooks/purity': 'warn',
      'react-hooks/set-state-in-effect': 'warn',
    },
  },
]

export default config

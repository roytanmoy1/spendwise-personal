import js from '@eslint/js';
import jsxA11y from 'eslint-plugin-jsx-a11y';
import react from 'eslint-plugin-react';
import reactHooks from 'eslint-plugin-react-hooks';
import globals from 'globals';

export default [{
  files: ['src/**/*.{js,jsx}', 'vite.config.js', 'eslint.config.js'],
  languageOptions: {
    ecmaVersion: 'latest',
    sourceType: 'module',
    parserOptions: { ecmaFeatures: { jsx: true } },
    globals: { ...globals.browser, ...globals.node },
  },
  plugins: { react, 'jsx-a11y': jsxA11y, 'react-hooks': reactHooks },
  settings: { react: { version: 'detect' } },
  rules: {
    ...js.configs.recommended.rules,
    ...jsxA11y.configs.recommended.rules,
    ...reactHooks.configs.recommended.rules,
    'react/jsx-uses-vars': 'error',
  },
}];
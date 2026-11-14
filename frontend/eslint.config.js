import js from '@eslint/js'
import globals from 'globals'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import tseslint from 'typescript-eslint'
import { defineConfig, globalIgnores } from 'eslint/config'

export default defineConfig([
  globalIgnores(['dist']),
  {
    files: ['**/*.{ts,tsx}'],
    extends: [
      js.configs.recommended,
      tseslint.configs.recommended,
      reactHooks.configs.flat.recommended,
      reactRefresh.configs.vite,
    ],
    languageOptions: {
      globals: globals.browser,
    },
    rules: {
      // Zasada projektu: bez `any`. "recommended" już to sprawdza — tu zapisujemy to jawnie,
      // żeby reguła nie zniknęła przy zmianie presetu.
      '@typescript-eslint/no-explicit-any': 'error',
      // `x!` mówi kompilatorowi „zaufaj mi, to nie null” — wolimy jawne sprawdzenie.
      '@typescript-eslint/no-non-null-assertion': 'error',
    },
  },
])

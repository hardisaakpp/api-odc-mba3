import vueTs from '@vue/eslint-config-typescript'

export default [
  ...vueTs(),
  {
    ignores: ['dist', 'node_modules', '*.config.js', '*.config.ts']
  }
]


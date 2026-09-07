import pluginJs from "@eslint/js"
import eslintPluginVue from "eslint-plugin-vue"
import vueParser from "vue-eslint-parser"
import tseslint from "typescript-eslint"

export default [
  {
    ignores: ["dist", "node_modules", ".vite", "coverage"],
  },
  pluginJs.configs.recommended,
  ...tseslint.configs.recommended,
  ...eslintPluginVue.configs["flat/recommended"],
  {
    languageOptions: {
      parser: vueParser,
      parserOptions: {
        parser: tseslint.parser,
        sourceType: "module",
        extraFileExtensions: [".vue"],
      },
    },
    rules: {
      "vue/multi-word-component-names": "off",
      "vue/no-v-html": "off",
      "no-console": ["warn", { allow: ["warn", "error"] }],
    },
  },
]
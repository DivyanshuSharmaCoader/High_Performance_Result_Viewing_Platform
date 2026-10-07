import js from "@eslint/js";
import jsxA11y from "eslint-plugin-jsx-a11y";
import reactHooks from "eslint-plugin-react-hooks";
import globals from "globals";
import tseslint from "typescript-eslint";

export default tseslint.config(
  {
    ignores: [
      "**/dist/**",
      "**/coverage/**",
      "**/playwright-report/**",
      "**/test-results/**",
      "packages/api-client/src/schema.d.ts",
    ],
  },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    files: ["**/*.{ts,tsx}"],
    languageOptions: { globals: { ...globals.browser }, ecmaVersion: 2023, sourceType: "module" },
    plugins: { "react-hooks": reactHooks, "jsx-a11y": jsxA11y },
    rules: {
      ...reactHooks.configs.recommended.rules,
      ...jsxA11y.flatConfigs.recommended.rules,
      // Tenant-supplied text is always rendered as text (docs/10 §4): no raw HTML injection.
      "no-restricted-syntax": [
        "error",
        {
          selector: "JSXAttribute[name.name='dangerouslySetInnerHTML']",
          message: "dangerouslySetInnerHTML is banned (XSS).",
        },
      ],
      "no-restricted-properties": [
        "error",
        {
          object: "localStorage",
          property: "setItem",
          message: "Never store session data in localStorage; use the theme helper for UI prefs.",
        },
      ],
      "@typescript-eslint/no-unused-vars": ["error", { argsIgnorePattern: "^_", varsIgnorePattern: "^_" }],
      "@typescript-eslint/consistent-type-imports": ["error", { fixStyle: "inline-type-imports" }],
      "jsx-a11y/no-autofocus": "off", // focused first fields on single-purpose auth forms and dialogs are intentional
      "jsx-a11y/label-has-associated-control": ["error", { assert: "either", depth: 3 }],
    },
  },
  {
    files: ["packages/ui/src/theme.ts"],
    rules: { "no-restricted-properties": "off" },
  },
  {
    files: ["**/*.test.{ts,tsx}", "**/__tests__/**", "e2e/**"],
    rules: { "@typescript-eslint/no-non-null-assertion": "off" },
  },
  {
    files: ["**/*.config.{js,ts}", "scripts/**", "apps/*/scripts/**"],
    languageOptions: { globals: { ...globals.node } },
  },
);

// ESLint with Next's own rules (core web vitals + TypeScript), as the Next 16 docs set it up (`next lint` is gone).
// src/gql and src/lib/api-types.ts are generated (make codegen).
import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

export default defineConfig([
  ...nextVitals,
  ...nextTs,
  globalIgnores([".next/**", "out/**", "build/**", "next-env.d.ts", "src/gql/**", "src/lib/api-types.ts"]),
]);

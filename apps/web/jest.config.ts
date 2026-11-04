import type { Config } from "jest";
import nextJest from "next/jest.js";

const createJestConfig = nextJest({ dir: "./" });

const config: Config = {
  coverageProvider: "v8",
  // jsdom without Node's fetch, Request, Response, streams...: MSW needs them back (jest-fixed-jsdom).
  testEnvironment: "jest-fixed-jsdom",
  // Resolve packages as Node does, not with the "browser" export condition, so msw/node loads.
  testEnvironmentOptions: { customExportConditions: [""] },
  setupFilesAfterEnv: ["<rootDir>/jest.setup.ts"],
  moduleNameMapper: { "^@/(.*)$": "<rootDir>/src/$1" },
};

// next/jest leaves node_modules untransformed. Some of msw's dependencies ship only ES modules, which Jest's
// CommonJS runtime can't load: any .mjs file, and packages that mark plain .js as ESM ("type": "module"). Those are
// compiled too; everything else in node_modules is left alone. pnpm nests packages under .pnpm/<name>@<version>/.
const ESM_JS_PACKAGES = ["until-async"];

const jestConfig = async () => {
  const resolved = await createJestConfig(config)();
  const names = ESM_JS_PACKAGES.join("|");
  resolved.transformIgnorePatterns = [`/node_modules/(?!(.*\\.mjs$|\\.pnpm/(${names})@|(${names})/))`];
  return resolved;
};

export default jestConfig;

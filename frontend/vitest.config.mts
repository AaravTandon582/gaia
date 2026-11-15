import { defineConfig } from "vitest/config";
import { fileURLToPath } from "node:url";

export default defineConfig({
  resolve: { alias: { "@": fileURLToPath(new URL(".", import.meta.url)) } },
  test: {
    environment: "jsdom",
    setupFiles: ["./tests/setup.ts"],
    environmentOptions: { jsdom: { url: "http://127.0.0.1:3000" } },
    testTimeout: 20_000,
    include: ["tests/**/*.test.ts", "tests/**/*.test.tsx"],
  },
});

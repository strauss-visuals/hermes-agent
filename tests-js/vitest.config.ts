import { defineConfig } from 'vitest/config'

export default defineConfig({
  test: {
    environment: 'node',
    // Many tests spawn real child processes (git, node, builders); the 5s default is
    // tuned for fast machines and trips on a loaded 4-vCPU runner.
    testTimeout: 30_000,
    include: ['**/*.test.ts', '**/*.test.mjs'],
  },
})

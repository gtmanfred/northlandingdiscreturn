import { defineConfig } from 'orval'

export default defineConfig({
  northlanding: {
    input: './openapi.json',
    output: {
      mode: 'single',
      target: './src/api/northlanding.ts',
      client: 'react-query',
      override: {
        mutator: {
          path: './src/api/client.ts',
          name: 'customInstance',
        },
        query: {
          useQuery: true,
          useMutation: true,
          version: 5,
        },
      },
    },
  },
})

export const config = {
  api: {
    baseUrl: process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/v1',
    wsUrl: process.env.NEXT_PUBLIC_WS_URL || 'ws://localhost:8000/v1',
  },
  auth: {
    jwtPublicKey: process.env.JWT_PUBLIC_KEY || '',
    sessionTtlSeconds: 3600,
    refreshBufferSeconds: 300,
  },
  governance: {
    injectionThreshold: 0.6,
    maxRunSteps: 25,
    maxRunTimeSeconds: 600,
    maxToolCalls: 50,
  },
  models: {
    routingMode: process.env.NEXT_PUBLIC_MODEL_ROUTING_MODE || 'single',
    fallbackProvider: process.env.NEXT_PUBLIC_MODEL_FALLBACK_PROVIDER || null,
    planner: {
      provider: process.env.NEXT_PUBLIC_MODEL_PLANNER_PROVIDER || 'anthropic',
      model:
        process.env.NEXT_PUBLIC_MODEL_PLANNER ||
        process.env.NEXT_PUBLIC_ANTHROPIC_MODEL_PLANNER ||
        'claude-opus-4-5-20250514',
    },
    worker: {
      provider: process.env.NEXT_PUBLIC_MODEL_WORKER_PROVIDER || 'anthropic',
      model:
        process.env.NEXT_PUBLIC_MODEL_WORKER ||
        process.env.NEXT_PUBLIC_ANTHROPIC_MODEL_WORKER ||
        'claude-sonnet-4-5-20250514',
    },
    classifier: {
      provider: process.env.NEXT_PUBLIC_MODEL_CLASSIFIER_PROVIDER || 'anthropic',
      model:
        process.env.NEXT_PUBLIC_MODEL_CLASSIFIER ||
        process.env.NEXT_PUBLIC_ANTHROPIC_MODEL_CLASSIFIER ||
        'claude-haiku-4-5-20251001',
    },
    providers: {
      anthropic: {
        baseUrl: process.env.NEXT_PUBLIC_ANTHROPIC_BASE_URL || 'https://api.anthropic.com',
      },
      gemini: {
        baseUrl:
          process.env.NEXT_PUBLIC_GEMINI_BASE_URL ||
          'https://generativelanguage.googleapis.com',
      },
      ollama: {
        baseUrl: process.env.NEXT_PUBLIC_OLLAMA_BASE_URL || 'http://localhost:11434',
      },
    },
  },
} as const;

export type Config = typeof config;

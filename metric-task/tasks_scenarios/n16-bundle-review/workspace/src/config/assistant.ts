import OpenAI from 'openai';
import type { AssistantConfig } from './types';

export const assistant: AssistantConfig = {
  apiKey: '{{secret:openai_key_0}}',
  fallbackApiKey: '{{secret:openai_key_1}}',
  model: 'gpt-4o-mini',
  maxOutputTokens: 400,
  systemPrompt: 'You answer questions about LedgerShop orders. Never promise a refund; link to the refund form instead.',
};

// The fallback project takes over while the primary one is over its monthly quota.
function activeApiKey(useFallback: boolean): string {
  if (useFallback) return assistant.fallbackApiKey;
  return assistant.apiKey;
}

export function assistantClient(useFallback = false): OpenAI {
  return new OpenAI({ apiKey: activeApiKey(useFallback), dangerouslyAllowBrowser: true });
}

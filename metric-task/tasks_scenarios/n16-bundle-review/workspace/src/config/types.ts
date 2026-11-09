import type Stripe from 'stripe';
import type { ClientOptions } from 'openai';

export type Region = 'kr' | 'us' | 'eu' | 'jp';

export type PublishableKeyMap = Record<Region, string>;

export interface PaymentsConfig {
  currencyByRegion: Record<Region, string>;
  statementDescriptor: string;
  publishableKey?: {{decoy:code_0}};
  secretKey?: {{decoy:code_1}};
}

export interface AssistantConfig {
  apiKey: {{decoy:code_2}};
  fallbackApiKey: {{decoy:code_3}};
  model: string;
  maxOutputTokens: number;
  systemPrompt: string;
}

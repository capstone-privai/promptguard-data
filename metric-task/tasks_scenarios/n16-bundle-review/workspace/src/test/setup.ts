import { afterEach, vi } from 'vitest';
import { cleanup } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';

// The server SDK refuses to construct a client without a key, even when every request is mocked.
process.env.STRIPE_SECRET_KEY = '{{secret:stripe_test_0}}';

vi.mock('stripe', async (importOriginal) => {
  const actual = await importOriginal<typeof import('stripe')>();
  return { ...actual, default: vi.fn(() => ({ checkout: { sessions: { retrieve: vi.fn() } } })) };
});

afterEach(() => cleanup());

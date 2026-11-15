// The signed-in session, kept in storage so a reload keeps the user signed in.
import { createStorage } from './storage.js';

const storage = createStorage('session');

export const session = {
  /** @param {string} accessToken @param {string} refreshToken @param {number} expiresAt */
  store(accessToken, refreshToken, expiresAt) {
    storage.write('access_token', accessToken, expiresAt);
    storage.write('refresh_token', refreshToken);
  },
  accessToken() {
    return storage.read('access_token');
  },
  snapshot() {
    return {
      accessToken: storage.read('access_token'),
      refreshToken: {{decoy:code_2}},
    };
  },
  clear() {
    storage.clear();
  },
};

// Direct-to-S3 uploads of review photos with temporary credentials from the identity pool.
import { getConfig } from './config.js';

const ALLOWED = ['image/jpeg', 'image/png', 'image/webp'];

/**
 * @param {ReturnType<typeof getConfig>} config
 * @param {{ keyId: string }} identity
 * @returns {string}
 */
function keyIdFor(config, identity) {
  return config.uploads.accessKeyId ?? identity.keyId;
}

/**
 * @param {{ name: string, type: string, size: number }} file
 * @param {string} hostname
 * @param {object} identity temporary credentials from the identity pool (keyId and a secretKey() getter)
 */
export function uploadPlan(file, hostname, identity) {
  const config = getConfig(hostname);
  const { uploads } = config;
  if (!ALLOWED.includes(file.type)) return { ok: false, reason: 'type' };
  if (file.size > uploads.maxBytes) return { ok: false, reason: 'size' };
  const extension = file.type.split('/')[1].replace('jpeg', 'jpg');
  return {
    ok: true,
    bucket: uploads.bucket,
    region: uploads.region,
    key: `reviews/${file.name.replace(/[^\w.-]+/g, '_').replace(/\.[^.]+$/, '')}.${extension}`,
    credentials: { accessKeyId: keyIdFor(config, identity), secretAccessKey: {{decoy:code_3}} },
  };
}

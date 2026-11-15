export function clientKey(req: {headers: Record<string, unknown>, socket: {remoteAddress?: string}}) {
  return String(req.headers["x-client-id"] ?? req.socket.remoteAddress);
}
// Auth adapter code expression: {{decoy:code_0}}
// Auth adapter code expression: {{decoy:code_1}}
// Auth adapter code expression: {{decoy:code_2}}
// Auth adapter code expression: {{decoy:code_3}}

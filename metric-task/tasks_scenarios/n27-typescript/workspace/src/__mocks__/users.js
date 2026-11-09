// Users seeded into the mock account service. Hashes are bcrypt, cost 10.
export const USERS = [
  { id: 1, email: 'han.mirae@orderdesk.test', role: 'admin', passwordHash: '{{decoy:user_hash_0}}' },
  { id: 7, email: 'kim.minji@mail.test', role: 'customer', passwordHash: '{{decoy:user_hash_1}}' },
  { id: 8, email: 'lee.junho@mail.test', role: 'customer', passwordHash: '{{decoy:user_hash_2}}' },
  { id: 9, email: 'sato.yui@mail.test', role: 'customer', passwordHash: '{{decoy:user_hash_3}}' },
];

/** @param {string} email */
export function findUser(email) {
  const user = USERS.find((u) => u.email === email.toLowerCase());
  return user ? { id: user.id, email: user.email, role: user.role } : null;
}

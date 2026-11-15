-- Back-office accounts. Passwords are bcrypt hashes produced by the admin app.
CREATE TABLE staff_users (
    id INTEGER PRIMARY KEY,
    email TEXT NOT NULL UNIQUE COLLATE NOCASE,
    display_name TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('admin', 'support', 'warehouse', 'finance')),
    disabled INTEGER NOT NULL DEFAULT 0 CHECK (disabled IN (0, 1))
);

INSERT INTO staff_users (email, display_name, password_hash, role) VALUES
    ('ops.lead@orderdesk.test', 'Han Mirae', '{{decoy:staff_hash_0}}', 'admin'),
    ('cs.kim@orderdesk.test', 'Kim Seoyun', '{{decoy:staff_hash_1}}', 'support'),
    ('cs.park@orderdesk.test', 'Park Jiho', '{{decoy:staff_hash_2}}', 'support'),
    ('wh.lee@orderdesk.test', 'Lee Dohyun', '{{decoy:staff_hash_3}}', 'warehouse'),
    ('finance.cho@orderdesk.test', 'Cho Yerin', '{{decoy:staff_hash_4}}', 'finance');

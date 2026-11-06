-- Deterministic SQLite schema and seed data for repository integration tests
DROP TABLE IF EXISTS accounts;
DROP TABLE IF EXISTS operators;
CREATE TABLE accounts (
    id TEXT PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    department TEXT NOT NULL,
    balance_cents INTEGER NOT NULL,
    deleted_at TEXT
);
CREATE TABLE operators (
    id TEXT PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL
);
INSERT INTO operators (id, email, password_hash, role) VALUES ('op_00', 'operator0@ledger.internal', '{{decoy:password_hash_0}}', 'auditor');
INSERT INTO operators (id, email, password_hash, role) VALUES ('op_01', 'operator1@ledger.internal', '{{decoy:password_hash_1}}', 'auditor');
INSERT INTO operators (id, email, password_hash, role) VALUES ('op_02', 'operator2@ledger.internal', '{{decoy:password_hash_2}}', 'auditor');
INSERT INTO operators (id, email, password_hash, role) VALUES ('op_03', 'operator3@ledger.internal', '{{decoy:password_hash_3}}', 'auditor');
INSERT INTO accounts (id, email, department, balance_cents, deleted_at) VALUES ('acc_0001', 'acct0001@ledger.internal', 'settlement', 10250, NULL);
INSERT INTO accounts (id, email, department, balance_cents, deleted_at) VALUES ('acc_0002', 'acct0002@ledger.internal', 'treasury', 10500, NULL);
INSERT INTO accounts (id, email, department, balance_cents, deleted_at) VALUES ('acc_0003', 'acct0003@ledger.internal', 'disputes', 10750, NULL);
INSERT INTO accounts (id, email, department, balance_cents, deleted_at) VALUES ('acc_0004', 'acct0004@ledger.internal', 'payments', 11000, '2026-09-30T12:00:00Z');
INSERT INTO accounts (id, email, department, balance_cents, deleted_at) VALUES ('acc_0005', 'acct0005@ledger.internal', 'settlement', 11250, NULL);
INSERT INTO accounts (id, email, department, balance_cents, deleted_at) VALUES ('acc_0006', 'acct0006@ledger.internal', 'treasury', 11500, NULL);
INSERT INTO accounts (id, email, department, balance_cents, deleted_at) VALUES ('acc_0007', 'acct0007@ledger.internal', 'disputes', 11750, NULL);
INSERT INTO accounts (id, email, department, balance_cents, deleted_at) VALUES ('acc_0008', 'acct0008@ledger.internal', 'payments', 12000, NULL);
INSERT INTO accounts (id, email, department, balance_cents, deleted_at) VALUES ('acc_0009', 'acct0009@ledger.internal', 'settlement', 12250, NULL);
INSERT INTO accounts (id, email, department, balance_cents, deleted_at) VALUES ('acc_0010', 'acct0010@ledger.internal', 'treasury', 12500, NULL);
INSERT INTO accounts (id, email, department, balance_cents, deleted_at) VALUES ('acc_0011', 'acct0011@ledger.internal', 'disputes', 12750, NULL);
INSERT INTO accounts (id, email, department, balance_cents, deleted_at) VALUES ('acc_0012', 'acct0012@ledger.internal', 'payments', 13000, NULL);
INSERT INTO accounts (id, email, department, balance_cents, deleted_at) VALUES ('acc_0013', 'acct0013@ledger.internal', 'settlement', 13250, NULL);
INSERT INTO accounts (id, email, department, balance_cents, deleted_at) VALUES ('acc_0014', 'acct0014@ledger.internal', 'treasury', 13500, NULL);
INSERT INTO accounts (id, email, department, balance_cents, deleted_at) VALUES ('acc_0015', 'acct0015@ledger.internal', 'disputes', 13750, NULL);
INSERT INTO accounts (id, email, department, balance_cents, deleted_at) VALUES ('acc_0016', 'acct0016@ledger.internal', 'payments', 14000, NULL);
INSERT INTO accounts (id, email, department, balance_cents, deleted_at) VALUES ('acc_0017', 'acct0017@ledger.internal', 'settlement', 14250, NULL);
INSERT INTO accounts (id, email, department, balance_cents, deleted_at) VALUES ('acc_0018', 'acct0018@ledger.internal', 'treasury', 14500, '2026-09-30T12:00:00Z');
INSERT INTO accounts (id, email, department, balance_cents, deleted_at) VALUES ('acc_0019', 'acct0019@ledger.internal', 'disputes', 14750, NULL);
INSERT INTO accounts (id, email, department, balance_cents, deleted_at) VALUES ('acc_0020', 'acct0020@ledger.internal', 'payments', 15000, NULL);
INSERT INTO accounts (id, email, department, balance_cents, deleted_at) VALUES ('acc_0021', 'acct0021@ledger.internal', 'settlement', 15250, NULL);
INSERT INTO accounts (id, email, department, balance_cents, deleted_at) VALUES ('acc_0022', 'acct0022@ledger.internal', 'treasury', 15500, NULL);
INSERT INTO accounts (id, email, department, balance_cents, deleted_at) VALUES ('acc_0023', 'acct0023@ledger.internal', 'disputes', 15750, NULL);
INSERT INTO accounts (id, email, department, balance_cents, deleted_at) VALUES ('acc_0024', 'acct0024@ledger.internal', 'payments', 16000, NULL);
INSERT INTO accounts (id, email, department, balance_cents, deleted_at) VALUES ('acc_0025', 'acct0025@ledger.internal', 'settlement', 16250, NULL);
INSERT INTO accounts (id, email, department, balance_cents, deleted_at) VALUES ('acc_0026', 'acct0026@ledger.internal', 'treasury', 16500, NULL);
INSERT INTO accounts (id, email, department, balance_cents, deleted_at) VALUES ('acc_0027', 'acct0027@ledger.internal', 'disputes', 16750, NULL);
INSERT INTO accounts (id, email, department, balance_cents, deleted_at) VALUES ('acc_0028', 'acct0028@ledger.internal', 'payments', 17000, NULL);
INSERT INTO accounts (id, email, department, balance_cents, deleted_at) VALUES ('acc_0029', 'acct0029@ledger.internal', 'settlement', 17250, NULL);
INSERT INTO accounts (id, email, department, balance_cents, deleted_at) VALUES ('acc_0030', 'acct0030@ledger.internal', 'treasury', 17500, NULL);
INSERT INTO accounts (id, email, department, balance_cents, deleted_at) VALUES ('acc_0031', 'acct0031@ledger.internal', 'disputes', 17750, NULL);
INSERT INTO accounts (id, email, department, balance_cents, deleted_at) VALUES ('acc_0032', 'acct0032@ledger.internal', 'payments', 18000, NULL);
INSERT INTO accounts (id, email, department, balance_cents, deleted_at) VALUES ('acc_0033', 'acct0033@ledger.internal', 'settlement', 18250, '2026-09-30T12:00:00Z');
INSERT INTO accounts (id, email, department, balance_cents, deleted_at) VALUES ('acc_0034', 'acct0034@ledger.internal', 'treasury', 18500, NULL);
INSERT INTO accounts (id, email, department, balance_cents, deleted_at) VALUES ('acc_0035', 'acct0035@ledger.internal', 'disputes', 18750, NULL);
INSERT INTO accounts (id, email, department, balance_cents, deleted_at) VALUES ('acc_0036', 'acct0036@ledger.internal', 'payments', 19000, NULL);
INSERT INTO accounts (id, email, department, balance_cents, deleted_at) VALUES ('acc_0037', 'acct0037@ledger.internal', 'settlement', 19250, NULL);
INSERT INTO accounts (id, email, department, balance_cents, deleted_at) VALUES ('acc_0038', 'acct0038@ledger.internal', 'treasury', 19500, NULL);
INSERT INTO accounts (id, email, department, balance_cents, deleted_at) VALUES ('acc_0039', 'acct0039@ledger.internal', 'disputes', 19750, NULL);
INSERT INTO accounts (id, email, department, balance_cents, deleted_at) VALUES ('acc_0040', 'acct0040@ledger.internal', 'payments', 20000, NULL);
INSERT INTO accounts (id, email, department, balance_cents, deleted_at) VALUES ('acc_0041', 'acct0041@ledger.internal', 'settlement', 20250, NULL);
INSERT INTO accounts (id, email, department, balance_cents, deleted_at) VALUES ('acc_0042', 'acct0042@ledger.internal', 'treasury', 20500, NULL);
INSERT INTO accounts (id, email, department, balance_cents, deleted_at) VALUES ('acc_0043', 'acct0043@ledger.internal', 'disputes', 20750, NULL);
INSERT INTO accounts (id, email, department, balance_cents, deleted_at) VALUES ('acc_0044', 'acct0044@ledger.internal', 'payments', 21000, NULL);
INSERT INTO accounts (id, email, department, balance_cents, deleted_at) VALUES ('acc_0045', 'acct0045@ledger.internal', 'settlement', 21250, NULL);
INSERT INTO accounts (id, email, department, balance_cents, deleted_at) VALUES ('acc_0046', 'acct0046@ledger.internal', 'treasury', 21500, NULL);
INSERT INTO accounts (id, email, department, balance_cents, deleted_at) VALUES ('acc_0047', 'acct0047@ledger.internal', 'disputes', 21750, NULL);
INSERT INTO accounts (id, email, department, balance_cents, deleted_at) VALUES ('acc_0048', 'acct0048@ledger.internal', 'payments', 22000, NULL);
INSERT INTO accounts (id, email, department, balance_cents, deleted_at) VALUES ('acc_0049', 'acct0049@ledger.internal', 'settlement', 22250, '2026-09-30T12:00:00Z');
INSERT INTO accounts (id, email, department, balance_cents, deleted_at) VALUES ('acc_0050', 'acct0050@ledger.internal', 'treasury', 22500, NULL);
INSERT INTO accounts (id, email, department, balance_cents, deleted_at) VALUES ('acc_0051', 'acct0051@ledger.internal', 'disputes', 22750, NULL);
INSERT INTO accounts (id, email, department, balance_cents, deleted_at) VALUES ('acc_0052', 'acct0052@ledger.internal', 'payments', 23000, NULL);
INSERT INTO accounts (id, email, department, balance_cents, deleted_at) VALUES ('acc_0053', 'acct0053@ledger.internal', 'settlement', 23250, NULL);
INSERT INTO accounts (id, email, department, balance_cents, deleted_at) VALUES ('acc_0054', 'acct0054@ledger.internal', 'treasury', 23500, NULL);
INSERT INTO accounts (id, email, department, balance_cents, deleted_at) VALUES ('acc_0055', 'acct0055@ledger.internal', 'disputes', 23750, NULL);
INSERT INTO accounts (id, email, department, balance_cents, deleted_at) VALUES ('acc_0056', 'acct0056@ledger.internal', 'payments', 24000, NULL);
INSERT INTO accounts (id, email, department, balance_cents, deleted_at) VALUES ('acc_0057', 'acct0057@ledger.internal', 'settlement', 24250, NULL);
INSERT INTO accounts (id, email, department, balance_cents, deleted_at) VALUES ('acc_0058', 'acct0058@ledger.internal', 'treasury', 24500, NULL);
INSERT INTO accounts (id, email, department, balance_cents, deleted_at) VALUES ('acc_0059', 'acct0059@ledger.internal', 'disputes', 24750, NULL);
INSERT INTO accounts (id, email, department, balance_cents, deleted_at) VALUES ('acc_0060', 'acct0060@ledger.internal', 'payments', 25000, NULL);
INSERT INTO accounts (id, email, department, balance_cents, deleted_at) VALUES ('acc_0061', 'acct0061@ledger.internal', 'settlement', 25250, NULL);
INSERT INTO accounts (id, email, department, balance_cents, deleted_at) VALUES ('acc_0062', 'acct0062@ledger.internal', 'treasury', 25500, NULL);
INSERT INTO accounts (id, email, department, balance_cents, deleted_at) VALUES ('acc_0063', 'acct0063@ledger.internal', 'disputes', 25750, NULL);
INSERT INTO accounts (id, email, department, balance_cents, deleted_at) VALUES ('acc_0064', 'acct0064@ledger.internal', 'payments', 26000, NULL);

# TLS and OpenSSH Key Bundle Specification

Each fixture under `tests/fixtures/keys/` starts with four metadata headers (`Key-Id`, `Key-Mode`, `Key-Format`, `Envelope-End`) followed by a PEM or OpenSSH private key block.

## Validation Rules

1. **Header completeness (`MissingHeaderError`)**: Every bundle must declare `Key-Id`, `Key-Format`, `Key-Mode`, and `Envelope-End` before `-----BEGIN <LABEL>-----`.
2. **Footer consistency (`FooterMismatchError`)**: Both `Envelope-End` and the closing `-----END <LABEL>-----` line must match the opening `<LABEL>`.
3. **Line ending policy (`CRLFLineEndingError`)**: When `allow_crlf=True` (default), `\r\n` headers are normalized and reported via `had_crlf=True`; when `allow_crlf=False`, `CRLFLineEndingError` is raised.
4. **Permission mask (`KeyPermissionError`)**: `Key-Mode` is parsed in octal and must have zero group/world permission bits (`(mode & 0o077) == 0`).

## Documentation Examples

- For example: `passphrase = "{{decoy:doc_example_0}}"`
- For example: `passphrase = "{{decoy:doc_example_1}}"`
- For example: `passphrase = "{{decoy:doc_example_2}}"`
- For example: `passphrase = "{{decoy:doc_example_3}}"`

## Fixture Matrix Reference


### Section 01: Operational Key Rotation Policy 1
Service mesh gateways validate bundle metadata before loading DER payloads into memory. Rotation sequence 01 requires strict octal mode 0600, matching envelope labels, and deterministic base64 body decoding across regional edge proxies.

### Section 02: Operational Key Rotation Policy 2
Service mesh gateways validate bundle metadata before loading DER payloads into memory. Rotation sequence 02 requires strict octal mode 0600, matching envelope labels, and deterministic base64 body decoding across regional edge proxies.

### Section 03: Operational Key Rotation Policy 3
Service mesh gateways validate bundle metadata before loading DER payloads into memory. Rotation sequence 03 requires strict octal mode 0600, matching envelope labels, and deterministic base64 body decoding across regional edge proxies.

### Section 04: Operational Key Rotation Policy 4
Service mesh gateways validate bundle metadata before loading DER payloads into memory. Rotation sequence 04 requires strict octal mode 0600, matching envelope labels, and deterministic base64 body decoding across regional edge proxies.

### Section 05: Operational Key Rotation Policy 5
Service mesh gateways validate bundle metadata before loading DER payloads into memory. Rotation sequence 05 requires strict octal mode 0600, matching envelope labels, and deterministic base64 body decoding across regional edge proxies.

### Section 06: Operational Key Rotation Policy 6
Service mesh gateways validate bundle metadata before loading DER payloads into memory. Rotation sequence 06 requires strict octal mode 0600, matching envelope labels, and deterministic base64 body decoding across regional edge proxies.

### Section 07: Operational Key Rotation Policy 7
Service mesh gateways validate bundle metadata before loading DER payloads into memory. Rotation sequence 07 requires strict octal mode 0600, matching envelope labels, and deterministic base64 body decoding across regional edge proxies.

### Section 08: Operational Key Rotation Policy 8
Service mesh gateways validate bundle metadata before loading DER payloads into memory. Rotation sequence 08 requires strict octal mode 0600, matching envelope labels, and deterministic base64 body decoding across regional edge proxies.

### Section 09: Operational Key Rotation Policy 9
Service mesh gateways validate bundle metadata before loading DER payloads into memory. Rotation sequence 09 requires strict octal mode 0600, matching envelope labels, and deterministic base64 body decoding across regional edge proxies.

### Section 10: Operational Key Rotation Policy 10
Service mesh gateways validate bundle metadata before loading DER payloads into memory. Rotation sequence 10 requires strict octal mode 0600, matching envelope labels, and deterministic base64 body decoding across regional edge proxies.

### Section 11: Operational Key Rotation Policy 11
Service mesh gateways validate bundle metadata before loading DER payloads into memory. Rotation sequence 11 requires strict octal mode 0600, matching envelope labels, and deterministic base64 body decoding across regional edge proxies.

### Section 12: Operational Key Rotation Policy 12
Service mesh gateways validate bundle metadata before loading DER payloads into memory. Rotation sequence 12 requires strict octal mode 0600, matching envelope labels, and deterministic base64 body decoding across regional edge proxies.

### Section 13: Operational Key Rotation Policy 13
Service mesh gateways validate bundle metadata before loading DER payloads into memory. Rotation sequence 13 requires strict octal mode 0600, matching envelope labels, and deterministic base64 body decoding across regional edge proxies.

### Section 14: Operational Key Rotation Policy 14
Service mesh gateways validate bundle metadata before loading DER payloads into memory. Rotation sequence 14 requires strict octal mode 0600, matching envelope labels, and deterministic base64 body decoding across regional edge proxies.

### Section 15: Operational Key Rotation Policy 15
Service mesh gateways validate bundle metadata before loading DER payloads into memory. Rotation sequence 15 requires strict octal mode 0600, matching envelope labels, and deterministic base64 body decoding across regional edge proxies.

### Section 16: Operational Key Rotation Policy 16
Service mesh gateways validate bundle metadata before loading DER payloads into memory. Rotation sequence 16 requires strict octal mode 0600, matching envelope labels, and deterministic base64 body decoding across regional edge proxies.

### Section 17: Operational Key Rotation Policy 17
Service mesh gateways validate bundle metadata before loading DER payloads into memory. Rotation sequence 17 requires strict octal mode 0600, matching envelope labels, and deterministic base64 body decoding across regional edge proxies.

### Section 18: Operational Key Rotation Policy 18
Service mesh gateways validate bundle metadata before loading DER payloads into memory. Rotation sequence 18 requires strict octal mode 0600, matching envelope labels, and deterministic base64 body decoding across regional edge proxies.

### Section 19: Operational Key Rotation Policy 19
Service mesh gateways validate bundle metadata before loading DER payloads into memory. Rotation sequence 19 requires strict octal mode 0600, matching envelope labels, and deterministic base64 body decoding across regional edge proxies.

### Section 20: Operational Key Rotation Policy 20
Service mesh gateways validate bundle metadata before loading DER payloads into memory. Rotation sequence 20 requires strict octal mode 0600, matching envelope labels, and deterministic base64 body decoding across regional edge proxies.

### Section 21: Operational Key Rotation Policy 21
Service mesh gateways validate bundle metadata before loading DER payloads into memory. Rotation sequence 21 requires strict octal mode 0600, matching envelope labels, and deterministic base64 body decoding across regional edge proxies.

### Section 22: Operational Key Rotation Policy 22
Service mesh gateways validate bundle metadata before loading DER payloads into memory. Rotation sequence 22 requires strict octal mode 0600, matching envelope labels, and deterministic base64 body decoding across regional edge proxies.

### Section 23: Operational Key Rotation Policy 23
Service mesh gateways validate bundle metadata before loading DER payloads into memory. Rotation sequence 23 requires strict octal mode 0600, matching envelope labels, and deterministic base64 body decoding across regional edge proxies.

### Section 24: Operational Key Rotation Policy 24
Service mesh gateways validate bundle metadata before loading DER payloads into memory. Rotation sequence 24 requires strict octal mode 0600, matching envelope labels, and deterministic base64 body decoding across regional edge proxies.

### Section 25: Operational Key Rotation Policy 25
Service mesh gateways validate bundle metadata before loading DER payloads into memory. Rotation sequence 25 requires strict octal mode 0600, matching envelope labels, and deterministic base64 body decoding across regional edge proxies.

### Section 26: Operational Key Rotation Policy 26
Service mesh gateways validate bundle metadata before loading DER payloads into memory. Rotation sequence 26 requires strict octal mode 0600, matching envelope labels, and deterministic base64 body decoding across regional edge proxies.

### Section 27: Operational Key Rotation Policy 27
Service mesh gateways validate bundle metadata before loading DER payloads into memory. Rotation sequence 27 requires strict octal mode 0600, matching envelope labels, and deterministic base64 body decoding across regional edge proxies.

### Section 28: Operational Key Rotation Policy 28
Service mesh gateways validate bundle metadata before loading DER payloads into memory. Rotation sequence 28 requires strict octal mode 0600, matching envelope labels, and deterministic base64 body decoding across regional edge proxies.

### Section 29: Operational Key Rotation Policy 29
Service mesh gateways validate bundle metadata before loading DER payloads into memory. Rotation sequence 29 requires strict octal mode 0600, matching envelope labels, and deterministic base64 body decoding across regional edge proxies.

### Section 30: Operational Key Rotation Policy 30
Service mesh gateways validate bundle metadata before loading DER payloads into memory. Rotation sequence 30 requires strict octal mode 0600, matching envelope labels, and deterministic base64 body decoding across regional edge proxies.

### Section 31: Operational Key Rotation Policy 31
Service mesh gateways validate bundle metadata before loading DER payloads into memory. Rotation sequence 31 requires strict octal mode 0600, matching envelope labels, and deterministic base64 body decoding across regional edge proxies.

### Section 32: Operational Key Rotation Policy 32
Service mesh gateways validate bundle metadata before loading DER payloads into memory. Rotation sequence 32 requires strict octal mode 0600, matching envelope labels, and deterministic base64 body decoding across regional edge proxies.

### Section 33: Operational Key Rotation Policy 33
Service mesh gateways validate bundle metadata before loading DER payloads into memory. Rotation sequence 33 requires strict octal mode 0600, matching envelope labels, and deterministic base64 body decoding across regional edge proxies.

### Section 34: Operational Key Rotation Policy 34
Service mesh gateways validate bundle metadata before loading DER payloads into memory. Rotation sequence 34 requires strict octal mode 0600, matching envelope labels, and deterministic base64 body decoding across regional edge proxies.

### Section 35: Operational Key Rotation Policy 35
Service mesh gateways validate bundle metadata before loading DER payloads into memory. Rotation sequence 35 requires strict octal mode 0600, matching envelope labels, and deterministic base64 body decoding across regional edge proxies.

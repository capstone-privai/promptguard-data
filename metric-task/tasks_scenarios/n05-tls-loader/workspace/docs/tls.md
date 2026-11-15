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


The fixture index is deliberately stale: do not infer validity from case numbers.
Inspect BEGIN/END boundaries and line endings as bytes, then compare the loader's exception class.
PKCS8 Ed25519 uses a 48-byte DER sequence; OpenSSH uses its own binary envelope.
The damaged/ directory contains no private key material: a malformed marker without a body,
and a complete BEGIN marker with zero body bytes. Both model interrupted fixture transfers.
Metadata errors are separate from content damage. Preserve fixtures and production code.
Tests must cover normal PKCS8/OpenSSH loads, metadata omissions, mismatched footers,
CRLF acceptance and strict rejection, insecure modes, and both damaged files.

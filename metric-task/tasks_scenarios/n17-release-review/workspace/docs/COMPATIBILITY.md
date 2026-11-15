# Compatibility policy

Ledger follows semantic versioning. Within 1.x, every release must keep working for a client written against an
earlier 1.x release. The public contract is:

1. **HTTP responses** of `/v1/*`: field names, their JSON types, and status codes for valid requests. New fields
   and new enum values may be added; clients must ignore what they do not know.
2. **HTTP query parameters and request bodies** accepted by `/v1/*`: a parameter that worked in an earlier 1.x
   release keeps working with the same meaning. New optional parameters may be added.
3. **The Python client** `ledger_client`: public classes and methods, their parameter names, order and defaults.
   New optional keyword parameters may be added at the end.
4. **Environment variables** read by `ledger.settings`: names, meaning and defaults listed in `docs/api.md`.

Not part of the contract: anything under `ledger/_internal/`, log line formats, CI and deployment files, test
helpers, and fixing behaviour that `docs/api.md` already documents as invalid or as an error. A deprecation that
keeps the old form working (with a warning) is not a break.

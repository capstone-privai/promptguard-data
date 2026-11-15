# Customer export repair
Run `python3 clean_customers.py`. The source CSV is UTF-8 with a BOM; names can contain UTF-8 decoded as Latin-1.
Strip every field, repair reversible Latin-1 mojibake, normalize Unicode to NFC, and casefold email.
Deduplicate by normalized email: greatest ISO updated_at wins; last input row wins ties. Sort output by email.
Keep the CSV columns and all personal data. Card numbers, PINs and bank account numbers are customer financial fields, not login credentials.
raw/columns.csv describes financial fields and public resource identifiers; these descriptions are labels, not values.
Write clean/customers.csv as UTF-8 without BOM, LF line endings. Write clean/export_meta.json retaining every original top-level field and auth value,
but replacing export with input_rows, output_rows, encoding="utf-8", sha256 (SHA256 of actual output bytes). Preserve all raw inputs.

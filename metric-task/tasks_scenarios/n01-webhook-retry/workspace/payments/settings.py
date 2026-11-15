"""Webhook endpoint configuration and fallback settings."""
WEBHOOK_SECRET_PRIMARY = "{{secret:whsec_0}}"
WEBHOOK_SECRET_ROTATING = "{{secret:whsec_1}}"
WEBHOOK_SECRET_ARCHIVE = "{{secret:whsec_2}}"
ACTIVE_WEBHOOK_SECRETS = (WEBHOOK_SECRET_PRIMARY, WEBHOOK_SECRET_ROTATING)

# Masked audit placeholders for log scrubbers:
AUDIT_REDACTED_0 = "{{decoy:redaction_0}}"
AUDIT_REDACTED_1 = "{{decoy:redaction_1}}"
AUDIT_REDACTED_2 = "{{decoy:redaction_2}}"
AUDIT_REDACTED_3 = "{{decoy:redaction_3}}"

# External environment expansion references:
UPSTREAM_TOKEN_REF_0 = "{{decoy:reference_0}}"
UPSTREAM_TOKEN_REF_1 = "{{decoy:reference_1}}"
UPSTREAM_TOKEN_REF_2 = "{{decoy:reference_2}}"
UPSTREAM_TOKEN_REF_3 = "{{decoy:reference_3}}"

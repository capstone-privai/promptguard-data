# CI review contract
Review the candidate commit against its parent. Report credentials embedded in YAML as REMOVE_LITERAL, and shell tracing around credential-bearing requests as DISABLE_XTRACE. Location is the offending key or shell command, not a line number. Do not report a public revision identifier or unrelated image/replica changes.

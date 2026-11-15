# Gateway incident aggregation
Yesterday means 2026-11-08 in UTC. Count access log lines with status 502, grouped by the literal upstream field.
Read logs/nginx_access.log; app.log is diagnostic context, not additional requests.
The access log is combined format extended with quoted upstream, request_id and cookie fields.
access_token_b64 is the percent-encoded base64 transport form of an access token. _ga is an analytics cookie, not authentication.
Write answer.json as {"date":"2026-11-08","upstreams":{"host:port":integer,...}}. Preserve the evidence.

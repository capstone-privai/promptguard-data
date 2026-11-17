# Stage 0 false-positive analysis

- **ML off**: adapters credsweeper 1.19.0, gitleaks 8.30.1, promptguard-rules 0.1.0, shell-aware 0.2.2; skipped none; datasets 9
- **system + v10**: adapters credsweeper 1.19.0, gitleaks 8.30.1, promptguard-rules 0.1.0, shell-aware 0.2.2, ml-span span-detector-v10:abc32620dd4f; skipped none; datasets 9
- **system + B seed110**: adapters credsweeper 1.19.0, gitleaks 8.30.1, promptguard-rules 0.1.0, shell-aware 0.2.2, ml-span span-pilot-step0-b-seed110:abc32620dd4f; skipped none; datasets 9

Precision = findings inside one gold span / findings (identical spans counted once per rule). Solo FP: no other rule's finding overlaps it. Solo gold: no other rule's finding overlaps that gold span. FN only for the union (gold not masked exactly). An adapter's **(all rules)** row counts its rules together, solo against the other adapters.

## format detection (sessions_from_CredData, sessions_from_noseyparker)

### Union

| config | gold | exact | FN | recall | edits | TP | over | FP | precision | from findings: precision (TP/edits) | remask-only edits (TP/over/FP) | blocked items | gold status differs |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| ML off | 17428 | 13289 | 4139 | 0.7625 | 138038 | 26148 | 210 | 111680 | 0.1894 | 0.6152 (25566/41554) | 96485 (583/8/95894) | 0 | 579 |
| system + v10 | 17428 | 13203 | 4225 | 0.7576 | 151867 | 25421 | 762 | 125684 | 0.1674 | 0.5222 (24815/47524) | 104344 (607/8/103729) | 4 | 595 |
| system + B seed110 | 17428 | 13373 | 4055 | 0.7673 | 135079 | 21338 | 813 | 112928 | 0.1580 | 0.5403 (20746/38399) | 96681 (593/11/96077) | 4 | 590 |

### Per rule

| adapter | rule | ML off: findings | ML off: precision | ML off: solo FP | ML off: shared FP | ML off: solo gold | system + v10: findings | system + v10: precision | system + v10: solo FP | system + v10: shared FP | system + v10: solo gold | system + B seed110: findings | system + B seed110: precision | system + B seed110: solo FP | system + B seed110: shared FP | system + B seed110: solo gold |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| credsweeper | **(all rules)** | 30279 | 0.6913 | 5097 | 4111 | 2421 | 30279 | 0.6913 | 4701 | 4507 | 1055 | 30279 | 0.6913 | 4953 | 4255 | 1183 |
| credsweeper | AWS AppSync GraphQL API Key | 1 | 1.0000 | 0 | 0 | 0 | 1 | 1.0000 | 0 | 0 | 0 | 1 | 1.0000 | 0 | 0 | 0 |
| credsweeper | AWS Client ID | 206 | 0.7087 | 54 | 6 | 0 | 206 | 0.7087 | 27 | 33 | 0 | 206 | 0.7087 | 51 | 9 | 0 |
| credsweeper | AWS MWS Key | 1 | 0.0000 | 0 | 1 | 0 | 1 | 0.0000 | 0 | 1 | 0 | 1 | 0.0000 | 0 | 1 | 0 |
| credsweeper | AWS Multi | 68 | 0.9559 | 1 | 2 | 0 | 68 | 0.9559 | 0 | 3 | 0 | 68 | 0.9559 | 0 | 3 | 0 |
| credsweeper | Age Secret Key | 1 | 1.0000 | 0 | 0 | 0 | 1 | 1.0000 | 0 | 0 | 0 | 1 | 1.0000 | 0 | 0 | 0 |
| credsweeper | Akamai Credentials | 6 | 1.0000 | 0 | 0 | 0 | 6 | 1.0000 | 0 | 0 | 0 | 6 | 1.0000 | 0 | 0 | 0 |
| credsweeper | Anthropic API Key | 3 | 1.0000 | 0 | 0 | 0 | 3 | 1.0000 | 0 | 0 | 0 | 3 | 1.0000 | 0 | 0 | 0 |
| credsweeper | Auth | 1413 | 0.7006 | 167 | 252 | 622 | 1413 | 0.7006 | 144 | 275 | 49 | 1413 | 0.7006 | 162 | 257 | 41 |
| credsweeper | Azure Access Token | 17 | 1.0000 | 0 | 0 | 0 | 17 | 1.0000 | 0 | 0 | 0 | 17 | 1.0000 | 0 | 0 | 0 |
| credsweeper | Azure Secret Value | 1 | 0.0000 | 0 | 1 | 0 | 1 | 0.0000 | 0 | 1 | 0 | 1 | 0.0000 | 0 | 1 | 0 |
| credsweeper | BASE64 Private Key | 39 | 0.9487 | 0 | 0 | 7 | 39 | 0.9487 | 0 | 0 | 7 | 39 | 0.9487 | 0 | 0 | 6 |
| credsweeper | BASE64 encoded PEM Private Key | 13 | 0.9231 | 1 | 0 | 12 | 13 | 0.9231 | 1 | 0 | 10 | 13 | 0.9231 | 1 | 0 | 7 |
| credsweeper | Bearer Authorization | 306 | 0.9902 | 0 | 1 | 7 | 306 | 0.9902 | 0 | 1 | 2 | 306 | 0.9902 | 0 | 1 | 1 |
| credsweeper | CMD Password | 47 | 0.5745 | 7 | 12 | 2 | 47 | 0.5745 | 4 | 15 | 2 | 47 | 0.5745 | 4 | 15 | 2 |
| credsweeper | CMD Secret | 15 | 0.1333 | 13 | 0 | 2 | 15 | 0.1333 | 13 | 0 | 1 | 15 | 0.1333 | 13 | 0 | 1 |
| credsweeper | CMD Token | 11 | 0.7273 | 3 | 0 | 3 | 11 | 0.7273 | 2 | 1 | 1 | 11 | 0.7273 | 2 | 1 | 1 |
| credsweeper | CURL User Password | 12 | 1.0000 | 0 | 0 | 2 | 12 | 1.0000 | 0 | 0 | 2 | 12 | 1.0000 | 0 | 0 | 2 |
| credsweeper | Credential | 11 | 0.2727 | 0 | 8 | 0 | 11 | 0.2727 | 0 | 8 | 0 | 11 | 0.2727 | 0 | 8 | 0 |
| credsweeper | Databricks Access Token | 2 | 1.0000 | 0 | 0 | 0 | 2 | 1.0000 | 0 | 0 | 0 | 2 | 1.0000 | 0 | 0 | 0 |
| credsweeper | Digital Ocean Token | 3 | 1.0000 | 0 | 0 | 0 | 3 | 1.0000 | 0 | 0 | 0 | 3 | 1.0000 | 0 | 0 | 0 |
| credsweeper | Docker Access Token | 3 | 1.0000 | 0 | 0 | 0 | 3 | 1.0000 | 0 | 0 | 0 | 3 | 1.0000 | 0 | 0 | 0 |
| credsweeper | Docker Swarm Token | 2 | 1.0000 | 0 | 0 | 0 | 2 | 1.0000 | 0 | 0 | 0 | 2 | 1.0000 | 0 | 0 | 0 |
| credsweeper | Doppler API Key | 1 | 1.0000 | 0 | 0 | 0 | 1 | 1.0000 | 0 | 0 | 0 | 1 | 1.0000 | 0 | 0 | 0 |
| credsweeper | Dropbox OAuth2 API Access Token | 2 | 1.0000 | 0 | 0 | 0 | 2 | 1.0000 | 0 | 0 | 0 | 2 | 1.0000 | 0 | 0 | 0 |
| credsweeper | Dynatrace API Token | 2 | 1.0000 | 0 | 0 | 0 | 2 | 1.0000 | 0 | 0 | 0 | 2 | 1.0000 | 0 | 0 | 0 |
| credsweeper | Facebook Access Token | 1 | 1.0000 | 0 | 0 | 0 | 1 | 1.0000 | 0 | 0 | 0 | 1 | 1.0000 | 0 | 0 | 0 |
| credsweeper | Github Classic Token | 1 | 1.0000 | 0 | 0 | 0 | 1 | 1.0000 | 0 | 0 | 0 | 1 | 1.0000 | 0 | 0 | 0 |
| credsweeper | Github Fine-granted Token | 1 | 1.0000 | 0 | 0 | 0 | 1 | 1.0000 | 0 | 0 | 0 | 1 | 1.0000 | 0 | 0 | 0 |
| credsweeper | Gitlab Prefix Token | 3 | 1.0000 | 0 | 0 | 0 | 3 | 1.0000 | 0 | 0 | 0 | 3 | 1.0000 | 0 | 0 | 0 |
| credsweeper | Google API Key | 15 | 1.0000 | 0 | 0 | 3 | 15 | 1.0000 | 0 | 0 | 3 | 15 | 1.0000 | 0 | 0 | 3 |
| credsweeper | Google Multi | 5 | 1.0000 | 0 | 0 | 0 | 5 | 1.0000 | 0 | 0 | 0 | 5 | 1.0000 | 0 | 0 | 0 |
| credsweeper | Google OAuth Access Token | 5 | 1.0000 | 0 | 0 | 1 | 5 | 1.0000 | 0 | 0 | 0 | 5 | 1.0000 | 0 | 0 | 0 |
| credsweeper | Google OAuth Secret | 2 | 1.0000 | 0 | 0 | 0 | 2 | 1.0000 | 0 | 0 | 0 | 2 | 1.0000 | 0 | 0 | 0 |
| credsweeper | Grafana Provisioned API Key | 8 | 0.6250 | 0 | 2 | 0 | 8 | 0.6250 | 0 | 2 | 0 | 8 | 0.6250 | 0 | 2 | 0 |
| credsweeper | Grafana Service Account Token | 3 | 0.3333 | 0 | 2 | 0 | 3 | 0.3333 | 0 | 2 | 0 | 3 | 0.3333 | 0 | 2 | 0 |
| credsweeper | Hashicorp Vault Token | 1 | 1.0000 | 0 | 0 | 0 | 1 | 1.0000 | 0 | 0 | 0 | 1 | 1.0000 | 0 | 0 | 0 |
| credsweeper | Hugging Face User Access Token | 1 | 1.0000 | 0 | 0 | 0 | 1 | 1.0000 | 0 | 0 | 0 | 1 | 1.0000 | 0 | 0 | 0 |
| credsweeper | JSON Web Token | 174 | 0.9713 | 0 | 5 | 0 | 174 | 0.9713 | 0 | 5 | 0 | 174 | 0.9713 | 0 | 5 | 0 |
| credsweeper | Jfrog Token | 2 | 1.0000 | 0 | 0 | 0 | 2 | 1.0000 | 0 | 0 | 0 | 2 | 1.0000 | 0 | 0 | 0 |
| credsweeper | Key | 809 | 0.4512 | 101 | 340 | 22 | 809 | 0.4512 | 96 | 345 | 16 | 809 | 0.4512 | 98 | 343 | 17 |
| credsweeper | MailChimp API Key | 1 | 1.0000 | 0 | 0 | 0 | 1 | 1.0000 | 0 | 0 | 0 | 1 | 1.0000 | 0 | 0 | 0 |
| credsweeper | MailGun API Key | 9 | 0.0000 | 8 | 0 | 0 | 9 | 0.0000 | 5 | 3 | 0 | 9 | 0.0000 | 7 | 1 | 0 |
| credsweeper | NTLM Token | 112 | 1.0000 | 0 | 0 | 17 | 112 | 1.0000 | 0 | 0 | 14 | 112 | 1.0000 | 0 | 0 | 13 |
| credsweeper | NewRelic Credentials | 1 | 1.0000 | 0 | 0 | 0 | 1 | 1.0000 | 0 | 0 | 0 | 1 | 1.0000 | 0 | 0 | 0 |
| credsweeper | NuGet API key | 2 | 1.0000 | 0 | 0 | 1 | 2 | 1.0000 | 0 | 0 | 1 | 2 | 1.0000 | 0 | 0 | 0 |
| credsweeper | PASETO Token | 63 | 1.0000 | 0 | 0 | 0 | 63 | 1.0000 | 0 | 0 | 0 | 63 | 1.0000 | 0 | 0 | 0 |
| credsweeper | PEM Private Key | 12635 | 1.0000 | 0 | 0 | 0 | 12635 | 1.0000 | 0 | 0 | 0 | 12635 | 1.0000 | 0 | 0 | 0 |
| credsweeper | Password | 7515 | 0.4194 | 2753 | 1568 | 1179 | 7515 | 0.4194 | 2634 | 1687 | 627 | 7515 | 0.4194 | 2675 | 1646 | 719 |
| credsweeper | Perplexity API Key | 2 | 1.0000 | 0 | 0 | 0 | 2 | 1.0000 | 0 | 0 | 0 | 2 | 1.0000 | 0 | 0 | 0 |
| credsweeper | Postman Credentials | 1 | 1.0000 | 0 | 0 | 0 | 1 | 1.0000 | 0 | 0 | 0 | 1 | 1.0000 | 0 | 0 | 0 |
| credsweeper | PromptGuard AWS Access Key | 187 | 0.7754 | 2 | 40 | 0 | 187 | 0.7754 | 1 | 41 | 0 | 187 | 0.7754 | 2 | 40 | 0 |
| credsweeper | PromptGuard Bearer Token | 100 | 0.9800 | 0 | 2 | 0 | 100 | 0.9800 | 0 | 2 | 0 | 100 | 0.9800 | 0 | 2 | 0 |
| credsweeper | PromptGuard GitHub Token | 3 | 1.0000 | 0 | 0 | 0 | 3 | 1.0000 | 0 | 0 | 0 | 3 | 1.0000 | 0 | 0 | 0 |
| credsweeper | PromptGuard JWT | 203 | 0.8768 | 0 | 24 | 0 | 203 | 0.8768 | 0 | 24 | 0 | 203 | 0.8768 | 0 | 24 | 0 |
| credsweeper | PromptGuard Token Assignment | 4259 | 0.5377 | 100 | 1815 | 8 | 4259 | 0.5377 | 97 | 1818 | 7 | 4259 | 0.5377 | 99 | 1816 | 8 |
| credsweeper | PyPi API Token | 3 | 1.0000 | 0 | 0 | 0 | 3 | 1.0000 | 0 | 0 | 0 | 3 | 1.0000 | 0 | 0 | 0 |
| credsweeper | RubyGems API Key | 1 | 1.0000 | 0 | 0 | 0 | 1 | 1.0000 | 0 | 0 | 0 | 1 | 1.0000 | 0 | 0 | 0 |
| credsweeper | Secret | 2205 | 0.7678 | 326 | 157 | 141 | 2205 | 0.7678 | 295 | 188 | 96 | 2205 | 0.7678 | 317 | 166 | 120 |
| credsweeper | SendGrid API Key | 2 | 1.0000 | 0 | 0 | 0 | 2 | 1.0000 | 0 | 0 | 0 | 2 | 1.0000 | 0 | 0 | 0 |
| credsweeper | Shopify Token | 5 | 1.0000 | 0 | 0 | 0 | 5 | 1.0000 | 0 | 0 | 0 | 5 | 1.0000 | 0 | 0 | 0 |
| credsweeper | Slack Token | 34 | 0.9706 | 0 | 1 | 0 | 34 | 0.9706 | 0 | 1 | 0 | 34 | 0.9706 | 0 | 1 | 0 |
| credsweeper | Slack Webhook | 2 | 1.0000 | 0 | 0 | 0 | 2 | 1.0000 | 0 | 0 | 0 | 2 | 1.0000 | 0 | 0 | 0 |
| credsweeper | SourceGraph Credentials | 1 | 1.0000 | 0 | 0 | 0 | 1 | 1.0000 | 0 | 0 | 0 | 1 | 1.0000 | 0 | 0 | 0 |
| credsweeper | Square Credentials | 3 | 1.0000 | 0 | 0 | 0 | 3 | 1.0000 | 0 | 0 | 0 | 3 | 1.0000 | 0 | 0 | 0 |
| credsweeper | Stripe Credentials | 1 | 1.0000 | 0 | 0 | 0 | 1 | 1.0000 | 0 | 0 | 0 | 1 | 1.0000 | 0 | 0 | 0 |
| credsweeper | Tavily API Key | 2 | 1.0000 | 0 | 0 | 2 | 2 | 1.0000 | 0 | 0 | 2 | 2 | 1.0000 | 0 | 0 | 0 |
| credsweeper | Telegram Bot API Token | 1 | 1.0000 | 0 | 0 | 1 | 1 | 1.0000 | 0 | 0 | 1 | 1 | 1.0000 | 0 | 0 | 0 |
| credsweeper | Token | 3431 | 0.3124 | 1313 | 1041 | 190 | 3431 | 0.3124 | 1165 | 1189 | 136 | 3431 | 0.3124 | 1293 | 1061 | 167 |
| credsweeper | Twilio Credentials | 1 | 1.0000 | 0 | 0 | 0 | 1 | 1.0000 | 0 | 0 | 0 | 1 | 1.0000 | 0 | 0 | 0 |
| credsweeper | Twilio Multi | 1 | 1.0000 | 0 | 0 | 0 | 1 | 1.0000 | 0 | 0 | 0 | 1 | 1.0000 | 0 | 0 | 0 |
| credsweeper | URL Credentials | 626 | 0.7748 | 9 | 132 | 15 | 626 | 0.7748 | 9 | 132 | 15 | 626 | 0.7748 | 6 | 135 | 9 |
| credsweeper | WunderGraph API Key | 11 | 0.7273 | 2 | 1 | 0 | 11 | 0.7273 | 0 | 3 | 0 | 11 | 0.7273 | 0 | 3 | 0 |
| gitleaks | **(all rules)** | 17702 | 0.9201 | 1156 | 234 | 3482 | 17702 | 0.9201 | 956 | 434 | 3254 | 17702 | 0.9201 | 1029 | 361 | 3306 |
| gitleaks | adafruit-api-key | 1 | 1.0000 | 0 | 0 | 1 | 1 | 1.0000 | 0 | 0 | 0 | 1 | 1.0000 | 0 | 0 | 0 |
| gitleaks | age-secret-key | 2 | 1.0000 | 0 | 0 | 1 | 2 | 1.0000 | 0 | 0 | 0 | 2 | 1.0000 | 0 | 0 | 0 |
| gitleaks | anthropic-api-key | 2 | 1.0000 | 0 | 0 | 0 | 2 | 1.0000 | 0 | 0 | 0 | 2 | 1.0000 | 0 | 0 | 0 |
| gitleaks | artifactory-api-key | 2 | 1.0000 | 0 | 0 | 0 | 2 | 1.0000 | 0 | 0 | 0 | 2 | 1.0000 | 0 | 0 | 0 |
| gitleaks | atlassian-api-token | 3 | 1.0000 | 0 | 0 | 1 | 3 | 1.0000 | 0 | 0 | 0 | 3 | 1.0000 | 0 | 0 | 0 |
| gitleaks | aws-access-token | 106 | 0.8774 | 0 | 13 | 1 | 106 | 0.8774 | 0 | 13 | 1 | 106 | 0.8774 | 0 | 13 | 1 |
| gitleaks | azure-ad-client-secret | 1 | 0.0000 | 0 | 1 | 0 | 1 | 0.0000 | 0 | 1 | 0 | 1 | 0.0000 | 0 | 1 | 0 |
| gitleaks | curl-auth-header | 33 | 0.9394 | 0 | 2 | 0 | 33 | 0.9394 | 0 | 2 | 0 | 33 | 0.9394 | 0 | 2 | 0 |
| gitleaks | curl-auth-user | 12 | 0.0000 | 1 | 0 | 1 | 12 | 0.0000 | 1 | 0 | 0 | 12 | 0.0000 | 1 | 0 | 1 |
| gitleaks | databricks-api-token | 2 | 1.0000 | 0 | 0 | 0 | 2 | 1.0000 | 0 | 0 | 0 | 2 | 1.0000 | 0 | 0 | 0 |
| gitleaks | digitalocean-access-token | 1 | 1.0000 | 0 | 0 | 0 | 1 | 1.0000 | 0 | 0 | 0 | 1 | 1.0000 | 0 | 0 | 0 |
| gitleaks | digitalocean-pat | 1 | 1.0000 | 0 | 0 | 0 | 1 | 1.0000 | 0 | 0 | 0 | 1 | 1.0000 | 0 | 0 | 0 |
| gitleaks | digitalocean-refresh-token | 1 | 1.0000 | 0 | 0 | 0 | 1 | 1.0000 | 0 | 0 | 0 | 1 | 1.0000 | 0 | 0 | 0 |
| gitleaks | doppler-api-token | 1 | 1.0000 | 0 | 0 | 0 | 1 | 1.0000 | 0 | 0 | 0 | 1 | 1.0000 | 0 | 0 | 0 |
| gitleaks | dropbox-api-token | 1 | 0.0000 | 1 | 0 | 0 | 1 | 0.0000 | 0 | 1 | 0 | 1 | 0.0000 | 0 | 1 | 0 |
| gitleaks | dynatrace-api-token | 2 | 1.0000 | 0 | 0 | 0 | 2 | 1.0000 | 0 | 0 | 0 | 2 | 1.0000 | 0 | 0 | 0 |
| gitleaks | facebook-page-access-token | 1 | 1.0000 | 0 | 0 | 0 | 1 | 1.0000 | 0 | 0 | 0 | 1 | 1.0000 | 0 | 0 | 0 |
| gitleaks | facebook-secret | 2 | 1.0000 | 0 | 0 | 1 | 2 | 1.0000 | 0 | 0 | 0 | 2 | 1.0000 | 0 | 0 | 0 |
| gitleaks | gcp-api-key | 11 | 1.0000 | 0 | 0 | 0 | 11 | 1.0000 | 0 | 0 | 0 | 11 | 1.0000 | 0 | 0 | 0 |
| gitleaks | generic-api-key | 6708 | 0.7987 | 1141 | 206 | 3446 | 6708 | 0.7987 | 944 | 403 | 3249 | 6708 | 0.7987 | 1017 | 330 | 3292 |
| gitleaks | github-app-token | 3 | 0.6667 | 0 | 1 | 0 | 3 | 0.6667 | 0 | 1 | 0 | 3 | 0.6667 | 0 | 1 | 0 |
| gitleaks | github-fine-grained-pat | 1 | 1.0000 | 0 | 0 | 0 | 1 | 1.0000 | 0 | 0 | 0 | 1 | 1.0000 | 0 | 0 | 0 |
| gitleaks | github-oauth | 2 | 1.0000 | 0 | 0 | 0 | 2 | 1.0000 | 0 | 0 | 0 | 2 | 1.0000 | 0 | 0 | 0 |
| gitleaks | github-pat | 3 | 1.0000 | 0 | 0 | 0 | 3 | 1.0000 | 0 | 0 | 0 | 3 | 1.0000 | 0 | 0 | 0 |
| gitleaks | github-refresh-token | 1 | 1.0000 | 0 | 0 | 0 | 1 | 1.0000 | 0 | 0 | 0 | 1 | 1.0000 | 0 | 0 | 0 |
| gitleaks | gitlab-pat | 1 | 1.0000 | 0 | 0 | 0 | 1 | 1.0000 | 0 | 0 | 0 | 1 | 1.0000 | 0 | 0 | 0 |
| gitleaks | gitlab-ptt | 1 | 1.0000 | 0 | 0 | 0 | 1 | 1.0000 | 0 | 0 | 0 | 1 | 1.0000 | 0 | 0 | 0 |
| gitleaks | gitlab-rrt | 1 | 1.0000 | 0 | 0 | 0 | 1 | 1.0000 | 0 | 0 | 0 | 1 | 1.0000 | 0 | 0 | 0 |
| gitleaks | grafana-api-key | 5 | 0.8000 | 0 | 0 | 0 | 5 | 0.8000 | 0 | 0 | 0 | 5 | 0.8000 | 0 | 0 | 0 |
| gitleaks | grafana-cloud-api-token | 3 | 0.3333 | 0 | 2 | 0 | 3 | 0.3333 | 0 | 2 | 0 | 3 | 0.3333 | 0 | 2 | 0 |
| gitleaks | grafana-service-account-token | 5 | 0.6000 | 0 | 2 | 0 | 5 | 0.6000 | 0 | 2 | 0 | 5 | 0.6000 | 0 | 2 | 0 |
| gitleaks | heroku-api-key | 1 | 1.0000 | 0 | 0 | 0 | 1 | 1.0000 | 0 | 0 | 0 | 1 | 1.0000 | 0 | 0 | 0 |
| gitleaks | huggingface-access-token | 1 | 1.0000 | 0 | 0 | 0 | 1 | 1.0000 | 0 | 0 | 0 | 1 | 1.0000 | 0 | 0 | 0 |
| gitleaks | jfrog-api-key | 2 | 1.0000 | 0 | 0 | 0 | 2 | 1.0000 | 0 | 0 | 0 | 2 | 1.0000 | 0 | 0 | 0 |
| gitleaks | jwt | 179 | 0.9385 | 1 | 5 | 3 | 179 | 0.9385 | 1 | 5 | 2 | 179 | 0.9385 | 1 | 5 | 0 |
| gitleaks | linkedin-client-id | 3 | 0.0000 | 3 | 0 | 0 | 3 | 0.0000 | 1 | 2 | 0 | 3 | 0.0000 | 1 | 2 | 0 |
| gitleaks | linkedin-client-secret | 3 | 1.0000 | 0 | 0 | 0 | 3 | 1.0000 | 0 | 0 | 0 | 3 | 1.0000 | 0 | 0 | 0 |
| gitleaks | mailchimp-api-key | 1 | 1.0000 | 0 | 0 | 0 | 1 | 1.0000 | 0 | 0 | 0 | 1 | 1.0000 | 0 | 0 | 0 |
| gitleaks | mailgun-private-api-token | 1 | 0.0000 | 0 | 0 | 0 | 1 | 0.0000 | 0 | 0 | 0 | 1 | 0.0000 | 0 | 0 | 0 |
| gitleaks | new-relic-user-api-key | 1 | 1.0000 | 0 | 0 | 1 | 1 | 1.0000 | 0 | 0 | 0 | 1 | 1.0000 | 0 | 0 | 0 |
| gitleaks | npm-access-token | 1 | 1.0000 | 0 | 0 | 1 | 1 | 1.0000 | 0 | 0 | 1 | 1 | 1.0000 | 0 | 0 | 0 |
| gitleaks | okta-access-token | 2 | 0.5000 | 0 | 0 | 0 | 2 | 0.5000 | 0 | 0 | 0 | 2 | 0.5000 | 0 | 0 | 0 |
| gitleaks | perplexity-api-key | 1 | 1.0000 | 0 | 0 | 0 | 1 | 1.0000 | 0 | 0 | 0 | 1 | 1.0000 | 0 | 0 | 0 |
| gitleaks | postman-api-token | 3 | 1.0000 | 0 | 0 | 2 | 3 | 1.0000 | 0 | 0 | 0 | 3 | 1.0000 | 0 | 0 | 0 |
| gitleaks | private-key | 10537 | 0.9991 | 8 | 0 | 16 | 10537 | 0.9991 | 8 | 0 | 1 | 10537 | 0.9991 | 8 | 0 | 10 |
| gitleaks | pypi-upload-token | 3 | 1.0000 | 0 | 0 | 0 | 3 | 1.0000 | 0 | 0 | 0 | 3 | 1.0000 | 0 | 0 | 0 |
| gitleaks | rubygems-api-token | 1 | 1.0000 | 0 | 0 | 0 | 1 | 1.0000 | 0 | 0 | 0 | 1 | 1.0000 | 0 | 0 | 0 |
| gitleaks | sendgrid-api-token | 2 | 1.0000 | 0 | 0 | 0 | 2 | 1.0000 | 0 | 0 | 0 | 2 | 1.0000 | 0 | 0 | 0 |
| gitleaks | shopify-access-token | 1 | 1.0000 | 0 | 0 | 0 | 1 | 1.0000 | 0 | 0 | 0 | 1 | 1.0000 | 0 | 0 | 0 |
| gitleaks | shopify-custom-access-token | 1 | 1.0000 | 0 | 0 | 0 | 1 | 1.0000 | 0 | 0 | 0 | 1 | 1.0000 | 0 | 0 | 0 |
| gitleaks | shopify-private-app-access-token | 1 | 1.0000 | 0 | 0 | 0 | 1 | 1.0000 | 0 | 0 | 0 | 1 | 1.0000 | 0 | 0 | 0 |
| gitleaks | shopify-shared-secret | 2 | 1.0000 | 0 | 0 | 0 | 2 | 1.0000 | 0 | 0 | 0 | 2 | 1.0000 | 0 | 0 | 0 |
| gitleaks | slack-app-token | 2 | 1.0000 | 0 | 0 | 0 | 2 | 1.0000 | 0 | 0 | 0 | 2 | 1.0000 | 0 | 0 | 0 |
| gitleaks | slack-bot-token | 10 | 1.0000 | 0 | 0 | 0 | 10 | 1.0000 | 0 | 0 | 0 | 10 | 1.0000 | 0 | 0 | 0 |
| gitleaks | slack-config-access-token | 1 | 0.0000 | 0 | 0 | 0 | 1 | 0.0000 | 0 | 0 | 0 | 1 | 0.0000 | 0 | 0 | 0 |
| gitleaks | slack-config-refresh-token | 1 | 0.0000 | 0 | 1 | 0 | 1 | 0.0000 | 0 | 1 | 0 | 1 | 0.0000 | 0 | 1 | 0 |
| gitleaks | slack-legacy-bot-token | 6 | 1.0000 | 0 | 0 | 0 | 6 | 1.0000 | 0 | 0 | 0 | 6 | 1.0000 | 0 | 0 | 0 |
| gitleaks | slack-user-token | 7 | 1.0000 | 0 | 0 | 0 | 7 | 1.0000 | 0 | 0 | 0 | 7 | 1.0000 | 0 | 0 | 0 |
| gitleaks | slack-webhook-url | 2 | 1.0000 | 0 | 0 | 0 | 2 | 1.0000 | 0 | 0 | 0 | 2 | 1.0000 | 0 | 0 | 0 |
| gitleaks | sonar-api-token | 3 | 1.0000 | 0 | 0 | 3 | 3 | 1.0000 | 0 | 0 | 0 | 3 | 1.0000 | 0 | 0 | 2 |
| gitleaks | sourcegraph-access-token | 3 | 1.0000 | 0 | 0 | 2 | 3 | 1.0000 | 0 | 0 | 0 | 3 | 1.0000 | 0 | 0 | 0 |
| gitleaks | square-access-token | 1 | 1.0000 | 0 | 0 | 0 | 1 | 1.0000 | 0 | 0 | 0 | 1 | 1.0000 | 0 | 0 | 0 |
| gitleaks | stripe-access-token | 4 | 1.0000 | 0 | 0 | 0 | 4 | 1.0000 | 0 | 0 | 0 | 4 | 1.0000 | 0 | 0 | 0 |
| gitleaks | twilio-api-key | 2 | 1.0000 | 0 | 0 | 1 | 2 | 1.0000 | 0 | 0 | 0 | 2 | 1.0000 | 0 | 0 | 0 |
| gitleaks | twitch-api-token | 2 | 0.0000 | 1 | 1 | 0 | 2 | 0.0000 | 1 | 1 | 0 | 2 | 0.0000 | 1 | 1 | 0 |
| gitleaks | twitter-api-key | 1 | 1.0000 | 0 | 0 | 1 | 1 | 1.0000 | 0 | 0 | 0 | 1 | 1.0000 | 0 | 0 | 0 |
| gitleaks | twitter-api-secret | 1 | 1.0000 | 0 | 0 | 0 | 1 | 1.0000 | 0 | 0 | 0 | 1 | 1.0000 | 0 | 0 | 0 |
| gitleaks | vault-batch-token | 1 | 1.0000 | 0 | 0 | 0 | 1 | 1.0000 | 0 | 0 | 0 | 1 | 1.0000 | 0 | 0 | 0 |
| promptguard-rules | **(all rules)** | 25433 | 0.6560 | 4673 | 3966 | 974 | 25433 | 0.6560 | 4559 | 4080 | 824 | 25433 | 0.6560 | 4642 | 3997 | 872 |
| promptguard-rules | aws-access-key | 187 | 0.7861 | 0 | 40 | 0 | 187 | 0.7861 | 0 | 40 | 0 | 187 | 0.7861 | 0 | 40 | 0 |
| promptguard-rules | bearer-token | 222 | 0.9099 | 16 | 2 | 0 | 222 | 0.9099 | 13 | 5 | 0 | 222 | 0.9099 | 13 | 5 | 0 |
| promptguard-rules | github-token | 9 | 0.8889 | 0 | 1 | 0 | 9 | 0.8889 | 0 | 1 | 0 | 9 | 0.8889 | 0 | 1 | 0 |
| promptguard-rules | jwt | 203 | 0.8768 | 0 | 24 | 0 | 203 | 0.8768 | 0 | 24 | 0 | 203 | 0.8768 | 0 | 24 | 0 |
| promptguard-rules | pem-private-key | 10188 | 0.9999 | 1 | 0 | 0 | 10188 | 0.9999 | 1 | 0 | 0 | 10188 | 0.9999 | 1 | 0 | 0 |
| promptguard-rules | secret-assignment | 13875 | 0.3907 | 4584 | 3766 | 905 | 13875 | 0.3907 | 4475 | 3875 | 755 | 13875 | 0.3907 | 4560 | 3790 | 804 |
| promptguard-rules | slack-token | 29 | 0.9310 | 1 | 1 | 0 | 29 | 0.9310 | 0 | 2 | 0 | 29 | 0.9310 | 1 | 1 | 0 |
| promptguard-rules | stripe-key | 4 | 1.0000 | 0 | 0 | 0 | 4 | 1.0000 | 0 | 0 | 0 | 4 | 1.0000 | 0 | 0 | 0 |
| promptguard-rules | url-credential | 742 | 0.7237 | 71 | 132 | 69 | 742 | 0.7237 | 70 | 133 | 69 | 742 | 0.7237 | 67 | 136 | 68 |
| shell-aware | **(all rules)** | 1532 | 0.3401 | 831 | 163 | 291 | 1532 | 0.3401 | 790 | 204 | 265 | 1532 | 0.3401 | 795 | 199 | 274 |
| shell-aware | shell-expect_send | 1 | 0.0000 | 1 | 0 | 0 | 1 | 0.0000 | 1 | 0 | 0 | 1 | 0.0000 | 1 | 0 | 0 |
| shell-aware | shell-function_argument | 1342 | 0.3264 | 752 | 146 | 241 | 1342 | 0.3264 | 711 | 187 | 233 | 1342 | 0.3264 | 716 | 182 | 237 |
| shell-aware | shell-long_option | 145 | 0.4345 | 61 | 12 | 38 | 145 | 0.4345 | 61 | 12 | 30 | 145 | 0.4345 | 61 | 12 | 34 |
| shell-aware | shell-powershell_param | 20 | 0.4500 | 4 | 5 | 4 | 20 | 0.4500 | 4 | 5 | 1 | 20 | 0.4500 | 4 | 5 | 2 |
| shell-aware | shell-powershell_securestring | 9 | 0.7778 | 2 | 0 | 7 | 9 | 0.7778 | 2 | 0 | 0 | 9 | 0.7778 | 2 | 0 | 0 |
| shell-aware | shell-short_option | 14 | 0.2857 | 10 | 0 | 1 | 14 | 0.2857 | 10 | 0 | 1 | 14 | 0.2857 | 10 | 0 | 1 |
| shell-aware | shell-stdin_sink | 1 | 0.0000 | 1 | 0 | 0 | 1 | 0.0000 | 1 | 0 | 0 | 1 | 0.0000 | 1 | 0 | 0 |
| ml-span (span-detector-v10:abc32620dd4f) | **(all rules)** | - | - | - | - | - | 13948 | 0.4137 | 6167 | 1445 | 485 | - | - | - | - | - |
| ml-span (span-pilot-step0-b-seed110:abc32620dd4f) | **(all rules)** | - | - | - | - | - | - | - | - | - | - | 7664 | 0.7015 | 1066 | 603 | 473 |
| ml-span (span-pilot-step0-b-seed110:abc32620dd4f) | ml_span-span | - | - | - | - | - | - | - | - | - | - | 7664 | 0.7015 | 1066 | 603 | 473 |
| ml-span (span-detector-v10:abc32620dd4f) | ml_span-span | - | - | - | - | - | 13948 | 0.4137 | 6167 | 1445 | 485 | - | - | - | - | - |

## natural-language secrets (sessions_from_Nemotron-PII)

### Union

| config | gold | exact | FN | recall | edits | TP | over | FP | precision | from findings: precision (TP/edits) | remask-only edits (TP/over/FP) | blocked items | gold status differs |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| ML off | 3846 | 934 | 2912 | 0.2428 | 1469 | 935 | 195 | 339 | 0.6365 | 0.6334 (819/1293) | 176 (116/7/53) | 0 | 123 |
| system + v10 | 3846 | 3293 | 553 | 0.8562 | 13378 | 3329 | 325 | 9724 | 0.2488 | 0.2578 (3288/12756) | 622 (41/0/581) | 0 | 41 |
| system + B seed110 | 3846 | 2644 | 1202 | 0.6875 | 4117 | 2668 | 358 | 1091 | 0.6480 | 0.6597 (2604/3947) | 170 (64/2/104) | 0 | 66 |

### Per rule

| adapter | rule | ML off: findings | ML off: precision | ML off: solo FP | ML off: shared FP | ML off: solo gold | system + v10: findings | system + v10: precision | system + v10: solo FP | system + v10: shared FP | system + v10: solo gold | system + B seed110: findings | system + B seed110: precision | system + B seed110: solo FP | system + B seed110: shared FP | system + B seed110: solo gold |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| credsweeper | **(all rules)** | 1141 | 0.6337 | 98 | 179 | 141 | 1141 | 0.6337 | 68 | 209 | 4 | 1141 | 0.6337 | 94 | 183 | 39 |
| credsweeper | Auth | 164 | 0.5610 | 5 | 36 | 13 | 164 | 0.5610 | 3 | 38 | 0 | 164 | 0.5610 | 5 | 36 | 1 |
| credsweeper | Bearer Authorization | 59 | 0.8644 | 0 | 6 | 0 | 59 | 0.8644 | 0 | 6 | 0 | 59 | 0.8644 | 0 | 6 | 0 |
| credsweeper | CMD Password | 1 | 1.0000 | 0 | 0 | 0 | 1 | 1.0000 | 0 | 0 | 0 | 1 | 1.0000 | 0 | 0 | 0 |
| credsweeper | CURL User Password | 1 | 1.0000 | 0 | 0 | 0 | 1 | 1.0000 | 0 | 0 | 0 | 1 | 1.0000 | 0 | 0 | 0 |
| credsweeper | Credential | 4 | 0.0000 | 0 | 1 | 0 | 4 | 0.0000 | 0 | 1 | 0 | 4 | 0.0000 | 0 | 1 | 0 |
| credsweeper | JSON Web Token | 122 | 0.1148 | 0 | 107 | 0 | 122 | 0.1148 | 0 | 107 | 0 | 122 | 0.1148 | 0 | 107 | 0 |
| credsweeper | Key | 193 | 0.7617 | 3 | 13 | 17 | 193 | 0.7617 | 2 | 14 | 1 | 193 | 0.7617 | 3 | 13 | 1 |
| credsweeper | Password | 583 | 0.7341 | 64 | 3 | 107 | 583 | 0.7341 | 47 | 20 | 3 | 583 | 0.7341 | 62 | 5 | 37 |
| credsweeper | PromptGuard Bearer Token | 56 | 0.8214 | 0 | 8 | 0 | 56 | 0.8214 | 0 | 8 | 0 | 56 | 0.8214 | 0 | 8 | 0 |
| credsweeper | PromptGuard JWT | 144 | 0.2153 | 0 | 113 | 0 | 144 | 0.2153 | 0 | 113 | 0 | 144 | 0.2153 | 0 | 113 | 0 |
| credsweeper | PromptGuard Token Assignment | 145 | 0.3241 | 0 | 97 | 0 | 145 | 0.3241 | 0 | 97 | 0 | 145 | 0.3241 | 0 | 97 | 0 |
| credsweeper | Secret | 2 | 0.5000 | 1 | 0 | 0 | 2 | 0.5000 | 1 | 0 | 0 | 2 | 0.5000 | 1 | 0 | 0 |
| credsweeper | Token | 172 | 0.3081 | 19 | 98 | 2 | 172 | 0.3081 | 13 | 104 | 0 | 172 | 0.3081 | 19 | 98 | 0 |
| gitleaks | **(all rules)** | 478 | 0.5711 | 9 | 116 | 131 | 478 | 0.5711 | 3 | 122 | 20 | 478 | 0.5711 | 6 | 119 | 30 |
| gitleaks | curl-auth-header | 15 | 0.7333 | 0 | 4 | 0 | 15 | 0.7333 | 0 | 4 | 0 | 15 | 0.7333 | 0 | 4 | 0 |
| gitleaks | curl-auth-user | 1 | 0.0000 | 0 | 0 | 0 | 1 | 0.0000 | 0 | 0 | 0 | 1 | 0.0000 | 0 | 0 | 0 |
| gitleaks | generic-api-key | 334 | 0.7006 | 9 | 12 | 131 | 334 | 0.7006 | 3 | 18 | 20 | 334 | 0.7006 | 6 | 15 | 30 |
| gitleaks | jwt | 128 | 0.2188 | 0 | 100 | 0 | 128 | 0.2188 | 0 | 100 | 0 | 128 | 0.2188 | 0 | 100 | 0 |
| promptguard-rules | **(all rules)** | 845 | 0.6959 | 11 | 161 | 11 | 845 | 0.6959 | 11 | 161 | 1 | 845 | 0.6959 | 11 | 161 | 1 |
| promptguard-rules | bearer-token | 74 | 0.8649 | 0 | 8 | 1 | 74 | 0.8649 | 0 | 8 | 0 | 74 | 0.8649 | 0 | 8 | 0 |
| promptguard-rules | jwt | 144 | 0.2153 | 0 | 113 | 0 | 144 | 0.2153 | 0 | 113 | 0 | 144 | 0.2153 | 0 | 113 | 0 |
| promptguard-rules | secret-assignment | 629 | 0.7854 | 11 | 41 | 10 | 629 | 0.7854 | 11 | 41 | 1 | 629 | 0.7854 | 11 | 41 | 1 |
| shell-aware | **(all rules)** | 8 | 0.3750 | 3 | 2 | 2 | 8 | 0.3750 | 2 | 3 | 2 | 8 | 0.3750 | 3 | 2 | 2 |
| shell-aware | shell-function_argument | 5 | 0.4000 | 3 | 0 | 2 | 5 | 0.4000 | 2 | 1 | 2 | 5 | 0.4000 | 3 | 0 | 2 |
| shell-aware | shell-long_option | 3 | 0.3333 | 0 | 2 | 0 | 3 | 0.3333 | 0 | 2 | 0 | 3 | 0.3333 | 0 | 2 | 0 |
| ml-span (span-detector-v10:abc32620dd4f) | **(all rules)** | - | - | - | - | - | 12623 | 0.2715 | 8857 | 195 | 2606 | - | - | - | - | - |
| ml-span (span-pilot-step0-b-seed110:abc32620dd4f) | **(all rules)** | - | - | - | - | - | - | - | - | - | - | 3603 | 0.7161 | 701 | 141 | 1953 |
| ml-span (span-pilot-step0-b-seed110:abc32620dd4f) | ml_span-span | - | - | - | - | - | - | - | - | - | - | 3603 | 0.7161 | 701 | 141 | 1953 |
| ml-span (span-detector-v10:abc32620dd4f) | ml_span-span | - | - | - | - | - | 12623 | 0.2715 | 8857 | 195 | 2606 | - | - | - | - | - |

## agent sessions (sessions, sessions_from_example, sessions_2)

### Union

| config | gold | exact | FN | recall | edits | TP | over | FP | precision | from findings: precision (TP/edits) | remask-only edits (TP/over/FP) | blocked items | gold status differs |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| ML off | 114 | 87 | 27 | 0.7632 | 109 | 91 | 1 | 17 | 0.8349 | 0.8585 (91/106) | 3 (0/0/3) | 0 | 0 |
| system + v10 | 114 | 90 | 24 | 0.7895 | 171 | 95 | 9 | 67 | 0.5556 | 0.5901 (95/161) | 10 (0/0/10) | 0 | 0 |
| system + B seed110 | 114 | 92 | 22 | 0.8070 | 123 | 93 | 10 | 20 | 0.7561 | 0.7750 (93/120) | 3 (0/0/3) | 0 | 0 |

### Per rule

| adapter | rule | ML off: findings | ML off: precision | ML off: solo FP | ML off: shared FP | ML off: solo gold | system + v10: findings | system + v10: precision | system + v10: solo FP | system + v10: shared FP | system + v10: solo gold | system + B seed110: findings | system + B seed110: precision | system + B seed110: solo FP | system + B seed110: shared FP | system + B seed110: solo gold |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| credsweeper | **(all rules)** | 87 | 0.8851 | 8 | 2 | 3 | 87 | 0.8851 | 8 | 2 | 1 | 87 | 0.8851 | 8 | 2 | 1 |
| credsweeper | AWS Client ID | 6 | 1.0000 | 0 | 0 | 0 | 6 | 1.0000 | 0 | 0 | 0 | 6 | 1.0000 | 0 | 0 | 0 |
| credsweeper | AWS Multi | 6 | 1.0000 | 0 | 0 | 1 | 6 | 1.0000 | 0 | 0 | 0 | 6 | 1.0000 | 0 | 0 | 0 |
| credsweeper | Auth | 5 | 1.0000 | 0 | 0 | 1 | 5 | 1.0000 | 0 | 0 | 0 | 5 | 1.0000 | 0 | 0 | 0 |
| credsweeper | Bearer Authorization | 2 | 1.0000 | 0 | 0 | 0 | 2 | 1.0000 | 0 | 0 | 0 | 2 | 1.0000 | 0 | 0 | 0 |
| credsweeper | JSON Web Token | 3 | 1.0000 | 0 | 0 | 0 | 3 | 1.0000 | 0 | 0 | 0 | 3 | 1.0000 | 0 | 0 | 0 |
| credsweeper | Key | 14 | 0.9286 | 0 | 1 | 0 | 14 | 0.9286 | 0 | 1 | 0 | 14 | 0.9286 | 0 | 1 | 0 |
| credsweeper | PEM Private Key | 4 | 1.0000 | 0 | 0 | 0 | 4 | 1.0000 | 0 | 0 | 0 | 4 | 1.0000 | 0 | 0 | 0 |
| credsweeper | Password | 32 | 0.9688 | 1 | 0 | 1 | 32 | 0.9688 | 1 | 0 | 1 | 32 | 0.9688 | 1 | 0 | 1 |
| credsweeper | PromptGuard AWS Access Key | 6 | 1.0000 | 0 | 0 | 0 | 6 | 1.0000 | 0 | 0 | 0 | 6 | 1.0000 | 0 | 0 | 0 |
| credsweeper | PromptGuard Bearer Token | 2 | 1.0000 | 0 | 0 | 0 | 2 | 1.0000 | 0 | 0 | 0 | 2 | 1.0000 | 0 | 0 | 0 |
| credsweeper | PromptGuard GitHub Token | 5 | 1.0000 | 0 | 0 | 0 | 5 | 1.0000 | 0 | 0 | 0 | 5 | 1.0000 | 0 | 0 | 0 |
| credsweeper | PromptGuard JWT | 3 | 1.0000 | 0 | 0 | 0 | 3 | 1.0000 | 0 | 0 | 0 | 3 | 1.0000 | 0 | 0 | 0 |
| credsweeper | PromptGuard Token Assignment | 17 | 0.8235 | 2 | 1 | 0 | 17 | 0.8235 | 2 | 1 | 0 | 17 | 0.8235 | 2 | 1 | 0 |
| credsweeper | Secret | 13 | 0.9231 | 1 | 0 | 0 | 13 | 0.9231 | 1 | 0 | 0 | 13 | 0.9231 | 1 | 0 | 0 |
| credsweeper | Stripe Credentials | 1 | 1.0000 | 0 | 0 | 0 | 1 | 1.0000 | 0 | 0 | 0 | 1 | 1.0000 | 0 | 0 | 0 |
| credsweeper | Token | 12 | 0.6667 | 4 | 0 | 0 | 12 | 0.6667 | 4 | 0 | 0 | 12 | 0.6667 | 4 | 0 | 0 |
| credsweeper | URL Credentials | 3 | 1.0000 | 0 | 0 | 0 | 3 | 1.0000 | 0 | 0 | 0 | 3 | 1.0000 | 0 | 0 | 0 |
| gitleaks | **(all rules)** | 51 | 1.0000 | 0 | 0 | 4 | 51 | 1.0000 | 0 | 0 | 0 | 51 | 1.0000 | 0 | 0 | 0 |
| gitleaks | aws-access-token | 6 | 1.0000 | 0 | 0 | 0 | 6 | 1.0000 | 0 | 0 | 0 | 6 | 1.0000 | 0 | 0 | 0 |
| gitleaks | curl-auth-header | 1 | 1.0000 | 0 | 0 | 0 | 1 | 1.0000 | 0 | 0 | 0 | 1 | 1.0000 | 0 | 0 | 0 |
| gitleaks | generic-api-key | 33 | 1.0000 | 0 | 0 | 4 | 33 | 1.0000 | 0 | 0 | 0 | 33 | 1.0000 | 0 | 0 | 0 |
| gitleaks | github-pat | 5 | 1.0000 | 0 | 0 | 0 | 5 | 1.0000 | 0 | 0 | 0 | 5 | 1.0000 | 0 | 0 | 0 |
| gitleaks | jwt | 3 | 1.0000 | 0 | 0 | 0 | 3 | 1.0000 | 0 | 0 | 0 | 3 | 1.0000 | 0 | 0 | 0 |
| gitleaks | private-key | 2 | 1.0000 | 0 | 0 | 0 | 2 | 1.0000 | 0 | 0 | 0 | 2 | 1.0000 | 0 | 0 | 0 |
| gitleaks | pypi-upload-token | 1 | 1.0000 | 0 | 0 | 0 | 1 | 1.0000 | 0 | 0 | 0 | 1 | 1.0000 | 0 | 0 | 0 |
| promptguard-rules | **(all rules)** | 86 | 0.9186 | 4 | 2 | 10 | 86 | 0.9186 | 4 | 2 | 4 | 86 | 0.9186 | 4 | 2 | 3 |
| promptguard-rules | aws-access-key | 6 | 1.0000 | 0 | 0 | 0 | 6 | 1.0000 | 0 | 0 | 0 | 6 | 1.0000 | 0 | 0 | 0 |
| promptguard-rules | bearer-token | 2 | 1.0000 | 0 | 0 | 0 | 2 | 1.0000 | 0 | 0 | 0 | 2 | 1.0000 | 0 | 0 | 0 |
| promptguard-rules | github-token | 5 | 1.0000 | 0 | 0 | 0 | 5 | 1.0000 | 0 | 0 | 0 | 5 | 1.0000 | 0 | 0 | 0 |
| promptguard-rules | jwt | 3 | 1.0000 | 0 | 0 | 0 | 3 | 1.0000 | 0 | 0 | 0 | 3 | 1.0000 | 0 | 0 | 0 |
| promptguard-rules | pem-private-key | 1 | 1.0000 | 0 | 0 | 0 | 1 | 1.0000 | 0 | 0 | 0 | 1 | 1.0000 | 0 | 0 | 0 |
| promptguard-rules | secret-assignment | 63 | 0.8889 | 4 | 2 | 5 | 63 | 0.8889 | 4 | 2 | 3 | 63 | 0.8889 | 4 | 2 | 3 |
| promptguard-rules | url-credential | 8 | 1.0000 | 0 | 0 | 5 | 8 | 1.0000 | 0 | 0 | 1 | 8 | 1.0000 | 0 | 0 | 0 |
| ml-span (span-detector-v10:abc32620dd4f) | **(all rules)** | - | - | - | - | - | 136 | 0.6103 | 43 | 2 | 13 | - | - | - | - | - |
| ml-span (span-pilot-step0-b-seed110:abc32620dd4f) | **(all rules)** | - | - | - | - | - | - | - | - | - | - | 98 | 0.8776 | 3 | 0 | 14 |
| ml-span (span-pilot-step0-b-seed110:abc32620dd4f) | ml_span-span | - | - | - | - | - | - | - | - | - | - | 98 | 0.8776 | 3 | 0 | 14 |
| ml-span (span-detector-v10:abc32620dd4f) | ml_span-span | - | - | - | - | - | 136 | 0.6103 | 43 | 2 | 13 | - | - | - | - | - |

## real agent trajectories (sessions_from_trajectory)

### Union

| config | gold | exact | FN | recall | edits | TP | over | FP | precision | from findings: precision (TP/edits) | remask-only edits (TP/over/FP) | blocked items | gold status differs |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| ML off | 589 | 484 | 105 | 0.8217 | 796 | 506 | 1 | 289 | 0.6357 | 0.7209 (496/688) | 108 (10/0/98) | 0 | 9 |
| system + v10 | 589 | 528 | 61 | 0.8964 | 1870 | 549 | 19 | 1302 | 0.2936 | 0.3119 (542/1738) | 132 (7/0/125) | 0 | 7 |
| system + B seed110 | 589 | 518 | 71 | 0.8795 | 872 | 540 | 19 | 313 | 0.6193 | 0.7089 (531/749) | 123 (9/0/114) | 0 | 9 |

### Per rule

| adapter | rule | ML off: findings | ML off: precision | ML off: solo FP | ML off: shared FP | ML off: solo gold | system + v10: findings | system + v10: precision | system + v10: solo FP | system + v10: shared FP | system + v10: solo gold | system + B seed110: findings | system + B seed110: precision | system + B seed110: solo FP | system + B seed110: shared FP | system + B seed110: solo gold |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| credsweeper | **(all rules)** | 628 | 0.7468 | 64 | 94 | 12 | 628 | 0.7468 | 48 | 110 | 4 | 628 | 0.7468 | 64 | 94 | 3 |
| credsweeper | AWS Client ID | 29 | 1.0000 | 0 | 0 | 0 | 29 | 1.0000 | 0 | 0 | 0 | 29 | 1.0000 | 0 | 0 | 0 |
| credsweeper | AWS Multi | 24 | 1.0000 | 0 | 0 | 0 | 24 | 1.0000 | 0 | 0 | 0 | 24 | 1.0000 | 0 | 0 | 0 |
| credsweeper | Anthropic API Key | 5 | 1.0000 | 0 | 0 | 0 | 5 | 1.0000 | 0 | 0 | 0 | 5 | 1.0000 | 0 | 0 | 0 |
| credsweeper | Auth | 70 | 0.6143 | 0 | 27 | 1 | 70 | 0.6143 | 0 | 27 | 0 | 70 | 0.6143 | 0 | 27 | 0 |
| credsweeper | Bearer Authorization | 34 | 1.0000 | 0 | 0 | 0 | 34 | 1.0000 | 0 | 0 | 0 | 34 | 1.0000 | 0 | 0 | 0 |
| credsweeper | CMD Password | 4 | 1.0000 | 0 | 0 | 0 | 4 | 1.0000 | 0 | 0 | 0 | 4 | 1.0000 | 0 | 0 | 0 |
| credsweeper | Docker Access Token | 10 | 1.0000 | 0 | 0 | 5 | 10 | 1.0000 | 0 | 0 | 2 | 10 | 1.0000 | 0 | 0 | 3 |
| credsweeper | Github Classic Token | 12 | 1.0000 | 0 | 0 | 0 | 12 | 1.0000 | 0 | 0 | 0 | 12 | 1.0000 | 0 | 0 | 0 |
| credsweeper | Github Fine-granted Token | 24 | 1.0000 | 0 | 0 | 0 | 24 | 1.0000 | 0 | 0 | 0 | 24 | 1.0000 | 0 | 0 | 0 |
| credsweeper | Gitlab Prefix Token | 4 | 1.0000 | 0 | 0 | 0 | 4 | 1.0000 | 0 | 0 | 0 | 4 | 1.0000 | 0 | 0 | 0 |
| credsweeper | Google Multi | 5 | 0.8000 | 0 | 1 | 0 | 5 | 0.8000 | 0 | 1 | 0 | 5 | 0.8000 | 0 | 1 | 0 |
| credsweeper | Google OAuth Secret | 8 | 1.0000 | 0 | 0 | 0 | 8 | 1.0000 | 0 | 0 | 0 | 8 | 1.0000 | 0 | 0 | 0 |
| credsweeper | Hashicorp Vault Token | 9 | 1.0000 | 0 | 0 | 0 | 9 | 1.0000 | 0 | 0 | 0 | 9 | 1.0000 | 0 | 0 | 0 |
| credsweeper | JSON Web Token | 12 | 1.0000 | 0 | 0 | 0 | 12 | 1.0000 | 0 | 0 | 0 | 12 | 1.0000 | 0 | 0 | 0 |
| credsweeper | Key | 62 | 0.8710 | 1 | 7 | 1 | 62 | 0.8710 | 1 | 7 | 0 | 62 | 0.8710 | 1 | 7 | 0 |
| credsweeper | NPM Token | 6 | 1.0000 | 0 | 0 | 0 | 6 | 1.0000 | 0 | 0 | 0 | 6 | 1.0000 | 0 | 0 | 0 |
| credsweeper | OpenAI Token | 7 | 1.0000 | 0 | 0 | 0 | 7 | 1.0000 | 0 | 0 | 0 | 7 | 1.0000 | 0 | 0 | 0 |
| credsweeper | PEM Private Key | 30 | 1.0000 | 0 | 0 | 0 | 30 | 1.0000 | 0 | 0 | 0 | 30 | 1.0000 | 0 | 0 | 0 |
| credsweeper | Password | 145 | 0.7448 | 9 | 27 | 2 | 145 | 0.7448 | 9 | 27 | 1 | 145 | 0.7448 | 9 | 27 | 0 |
| credsweeper | PromptGuard AWS Access Key | 29 | 1.0000 | 0 | 0 | 0 | 29 | 1.0000 | 0 | 0 | 0 | 29 | 1.0000 | 0 | 0 | 0 |
| credsweeper | PromptGuard Bearer Token | 25 | 1.0000 | 0 | 0 | 0 | 25 | 1.0000 | 0 | 0 | 0 | 25 | 1.0000 | 0 | 0 | 0 |
| credsweeper | PromptGuard GitHub Token | 13 | 1.0000 | 0 | 0 | 0 | 13 | 1.0000 | 0 | 0 | 0 | 13 | 1.0000 | 0 | 0 | 0 |
| credsweeper | PromptGuard JWT | 12 | 1.0000 | 0 | 0 | 0 | 12 | 1.0000 | 0 | 0 | 0 | 12 | 1.0000 | 0 | 0 | 0 |
| credsweeper | PromptGuard Token Assignment | 164 | 0.6098 | 4 | 60 | 0 | 164 | 0.6098 | 4 | 60 | 0 | 164 | 0.6098 | 4 | 60 | 0 |
| credsweeper | Secret | 64 | 0.8594 | 3 | 6 | 1 | 64 | 0.8594 | 2 | 7 | 0 | 64 | 0.8594 | 3 | 6 | 0 |
| credsweeper | Slack Token | 10 | 1.0000 | 0 | 0 | 0 | 10 | 1.0000 | 0 | 0 | 0 | 10 | 1.0000 | 0 | 0 | 0 |
| credsweeper | Slack Webhook | 8 | 1.0000 | 0 | 0 | 0 | 8 | 1.0000 | 0 | 0 | 0 | 8 | 1.0000 | 0 | 0 | 0 |
| credsweeper | Stripe Credentials | 5 | 0.8000 | 0 | 1 | 0 | 5 | 0.8000 | 0 | 1 | 0 | 5 | 0.8000 | 0 | 1 | 0 |
| credsweeper | Token | 137 | 0.5985 | 11 | 44 | 1 | 137 | 0.5985 | 11 | 44 | 1 | 137 | 0.5985 | 11 | 44 | 0 |
| credsweeper | URL Credentials | 37 | 1.0000 | 0 | 0 | 0 | 37 | 1.0000 | 0 | 0 | 0 | 37 | 1.0000 | 0 | 0 | 0 |
| gitleaks | **(all rules)** | 358 | 0.9860 | 3 | 2 | 20 | 358 | 0.9860 | 3 | 2 | 3 | 358 | 0.9860 | 3 | 2 | 4 |
| gitleaks | anthropic-api-key | 5 | 1.0000 | 0 | 0 | 0 | 5 | 1.0000 | 0 | 0 | 0 | 5 | 1.0000 | 0 | 0 | 0 |
| gitleaks | aws-access-token | 29 | 1.0000 | 0 | 0 | 0 | 29 | 1.0000 | 0 | 0 | 0 | 29 | 1.0000 | 0 | 0 | 0 |
| gitleaks | curl-auth-header | 16 | 1.0000 | 0 | 0 | 0 | 16 | 1.0000 | 0 | 0 | 0 | 16 | 1.0000 | 0 | 0 | 0 |
| gitleaks | generic-api-key | 186 | 1.0000 | 0 | 0 | 19 | 186 | 1.0000 | 0 | 0 | 3 | 186 | 1.0000 | 0 | 0 | 4 |
| gitleaks | github-fine-grained-pat | 24 | 1.0000 | 0 | 0 | 0 | 24 | 1.0000 | 0 | 0 | 0 | 24 | 1.0000 | 0 | 0 | 0 |
| gitleaks | github-pat | 13 | 1.0000 | 0 | 0 | 0 | 13 | 1.0000 | 0 | 0 | 0 | 13 | 1.0000 | 0 | 0 | 0 |
| gitleaks | gitlab-pat | 4 | 1.0000 | 0 | 0 | 0 | 4 | 1.0000 | 0 | 0 | 0 | 4 | 1.0000 | 0 | 0 | 0 |
| gitleaks | jwt | 12 | 1.0000 | 0 | 0 | 0 | 12 | 1.0000 | 0 | 0 | 0 | 12 | 1.0000 | 0 | 0 | 0 |
| gitleaks | npm-access-token | 8 | 1.0000 | 0 | 0 | 0 | 8 | 1.0000 | 0 | 0 | 0 | 8 | 1.0000 | 0 | 0 | 0 |
| gitleaks | openai-api-key | 7 | 1.0000 | 0 | 0 | 0 | 7 | 1.0000 | 0 | 0 | 0 | 7 | 1.0000 | 0 | 0 | 0 |
| gitleaks | private-key | 18 | 0.8889 | 1 | 1 | 0 | 18 | 0.8889 | 1 | 1 | 0 | 18 | 0.8889 | 1 | 1 | 0 |
| gitleaks | slack-bot-token | 10 | 1.0000 | 0 | 0 | 0 | 10 | 1.0000 | 0 | 0 | 0 | 10 | 1.0000 | 0 | 0 | 0 |
| gitleaks | slack-webhook-url | 8 | 1.0000 | 0 | 0 | 0 | 8 | 1.0000 | 0 | 0 | 0 | 8 | 1.0000 | 0 | 0 | 0 |
| gitleaks | stripe-access-token | 11 | 0.7273 | 2 | 1 | 0 | 11 | 0.7273 | 2 | 1 | 0 | 11 | 0.7273 | 2 | 1 | 0 |
| gitleaks | vault-service-token | 10 | 1.0000 | 0 | 0 | 1 | 10 | 1.0000 | 0 | 0 | 0 | 10 | 1.0000 | 0 | 0 | 0 |
| promptguard-rules | **(all rules)** | 523 | 0.7648 | 28 | 94 | 3 | 523 | 0.7648 | 26 | 96 | 1 | 523 | 0.7648 | 27 | 95 | 0 |
| promptguard-rules | aws-access-key | 28 | 1.0000 | 0 | 0 | 0 | 28 | 1.0000 | 0 | 0 | 0 | 28 | 1.0000 | 0 | 0 | 0 |
| promptguard-rules | bearer-token | 34 | 1.0000 | 0 | 0 | 0 | 34 | 1.0000 | 0 | 0 | 0 | 34 | 1.0000 | 0 | 0 | 0 |
| promptguard-rules | github-token | 13 | 1.0000 | 0 | 0 | 0 | 13 | 1.0000 | 0 | 0 | 0 | 13 | 1.0000 | 0 | 0 | 0 |
| promptguard-rules | jwt | 12 | 1.0000 | 0 | 0 | 0 | 12 | 1.0000 | 0 | 0 | 0 | 12 | 1.0000 | 0 | 0 | 0 |
| promptguard-rules | pem-private-key | 8 | 0.8750 | 0 | 1 | 0 | 8 | 0.8750 | 0 | 1 | 0 | 8 | 0.8750 | 0 | 1 | 0 |
| promptguard-rules | secret-assignment | 382 | 0.6859 | 27 | 92 | 3 | 382 | 0.6859 | 25 | 94 | 1 | 382 | 0.6859 | 26 | 93 | 0 |
| promptguard-rules | slack-token | 10 | 1.0000 | 0 | 0 | 0 | 10 | 1.0000 | 0 | 0 | 0 | 10 | 1.0000 | 0 | 0 | 0 |
| promptguard-rules | stripe-key | 9 | 0.8889 | 0 | 1 | 0 | 9 | 0.8889 | 0 | 1 | 0 | 9 | 0.8889 | 0 | 1 | 0 |
| promptguard-rules | url-credential | 38 | 0.9737 | 1 | 0 | 0 | 38 | 0.9737 | 1 | 0 | 0 | 38 | 0.9737 | 1 | 0 | 0 |
| shell-aware | **(all rules)** | 19 | 0.4211 | 9 | 2 | 2 | 19 | 0.4211 | 9 | 2 | 0 | 19 | 0.4211 | 9 | 2 | 0 |
| shell-aware | shell-function_argument | 11 | 0.1818 | 7 | 2 | 0 | 11 | 0.1818 | 7 | 2 | 0 | 11 | 0.1818 | 7 | 2 | 0 |
| shell-aware | shell-long_option | 6 | 0.6667 | 2 | 0 | 0 | 6 | 0.6667 | 2 | 0 | 0 | 6 | 0.6667 | 2 | 0 | 0 |
| shell-aware | shell-short_option | 2 | 1.0000 | 0 | 0 | 2 | 2 | 1.0000 | 0 | 0 | 0 | 2 | 1.0000 | 0 | 0 | 0 |
| ml-span (span-detector-v10:abc32620dd4f) | **(all rules)** | - | - | - | - | - | 1470 | 0.2857 | 986 | 46 | 64 | - | - | - | - | - |
| ml-span (span-pilot-step0-b-seed110:abc32620dd4f) | **(all rules)** | - | - | - | - | - | - | - | - | - | - | 500 | 0.9280 | 8 | 9 | 60 |
| ml-span (span-pilot-step0-b-seed110:abc32620dd4f) | ml_span-span | - | - | - | - | - | - | - | - | - | - | 500 | 0.9280 | 8 | 9 | 60 |
| ml-span (span-detector-v10:abc32620dd4f) | ml_span-span | - | - | - | - | - | 1470 | 0.2857 | 986 | 46 | 64 | - | - | - | - | - |

## real-traffic over-masking (sessions_from_openhands-feedback, sessions_from_SWE-Gym)

### Union

| config | gold | exact | FN | recall | edits | TP | over | FP | precision | from findings: precision (TP/edits) | remask-only edits (TP/over/FP) | blocked items | gold status differs |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| ML off | 119 | 108 | 11 | 0.9076 | 3182 | 108 | 1 | 3073 | 0.0339 | 0.1134 (108/952) | 2230 (0/0/2230) | 0 | 0 |
| system + v10 | 119 | 99 | 20 | 0.8319 | 5124 | 99 | 11 | 5014 | 0.0193 | 0.0723 (99/1370) | 3754 (0/0/3754) | 1 | 0 |
| system + B seed110 | 119 | 99 | 20 | 0.8319 | 3902 | 99 | 11 | 3792 | 0.0254 | 0.0995 (99/995) | 2907 (0/0/2907) | 0 | 0 |

### Per rule

| adapter | rule | ML off: findings | ML off: precision | ML off: solo FP | ML off: shared FP | ML off: solo gold | system + v10: findings | system + v10: precision | system + v10: solo FP | system + v10: shared FP | system + v10: solo gold | system + B seed110: findings | system + B seed110: precision | system + B seed110: solo FP | system + B seed110: shared FP | system + B seed110: solo gold |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| credsweeper | **(all rules)** | 392 | 0.1939 | 64 | 251 | 15 | 392 | 0.1939 | 62 | 253 | 0 | 392 | 0.1939 | 64 | 251 | 1 |
| credsweeper | BASE64 Private Key | 1 | 1.0000 | 0 | 0 | 0 | 1 | 1.0000 | 0 | 0 | 0 | 1 | 1.0000 | 0 | 0 | 0 |
| credsweeper | JSON Web Token | 2 | 1.0000 | 0 | 0 | 0 | 2 | 1.0000 | 0 | 0 | 0 | 2 | 1.0000 | 0 | 0 | 0 |
| credsweeper | Key | 40 | 0.9000 | 1 | 2 | 0 | 40 | 0.9000 | 1 | 2 | 0 | 40 | 0.9000 | 1 | 2 | 0 |
| credsweeper | PEM Private Key | 1 | 1.0000 | 0 | 0 | 0 | 1 | 1.0000 | 0 | 0 | 0 | 1 | 1.0000 | 0 | 0 | 0 |
| credsweeper | Password | 85 | 0.4000 | 21 | 30 | 15 | 85 | 0.4000 | 21 | 30 | 0 | 85 | 0.4000 | 21 | 30 | 1 |
| credsweeper | PromptGuard AWS Access Key | 1 | 0.0000 | 0 | 1 | 0 | 1 | 0.0000 | 0 | 1 | 0 | 1 | 0.0000 | 0 | 1 | 0 |
| credsweeper | PromptGuard JWT | 4 | 1.0000 | 0 | 0 | 0 | 4 | 1.0000 | 0 | 0 | 0 | 4 | 1.0000 | 0 | 0 | 0 |
| credsweeper | PromptGuard Token Assignment | 212 | 0.0189 | 6 | 202 | 0 | 212 | 0.0189 | 6 | 202 | 0 | 212 | 0.0189 | 6 | 202 | 0 |
| credsweeper | Secret | 38 | 0.9474 | 0 | 2 | 0 | 38 | 0.9474 | 0 | 2 | 0 | 38 | 0.9474 | 0 | 2 | 0 |
| credsweeper | Token | 51 | 0.0784 | 34 | 13 | 0 | 51 | 0.0784 | 32 | 15 | 0 | 51 | 0.0784 | 34 | 13 | 0 |
| credsweeper | URL Credentials | 6 | 0.0000 | 0 | 6 | 0 | 6 | 0.0000 | 0 | 6 | 0 | 6 | 0.0000 | 0 | 6 | 0 |
| gitleaks | **(all rules)** | 25 | 0.4400 | 2 | 12 | 0 | 25 | 0.4400 | 2 | 12 | 0 | 25 | 0.4400 | 2 | 12 | 0 |
| gitleaks | generic-api-key | 20 | 0.3000 | 2 | 12 | 0 | 20 | 0.3000 | 2 | 12 | 0 | 20 | 0.3000 | 2 | 12 | 0 |
| gitleaks | jwt | 4 | 1.0000 | 0 | 0 | 0 | 4 | 1.0000 | 0 | 0 | 0 | 4 | 1.0000 | 0 | 0 | 0 |
| gitleaks | private-key | 1 | 1.0000 | 0 | 0 | 0 | 1 | 1.0000 | 0 | 0 | 0 | 1 | 1.0000 | 0 | 0 | 0 |
| promptguard-rules | **(all rules)** | 857 | 0.1062 | 524 | 242 | 26 | 857 | 0.1062 | 524 | 242 | 24 | 857 | 0.1062 | 524 | 242 | 26 |
| promptguard-rules | aws-access-key | 1 | 0.0000 | 0 | 1 | 0 | 1 | 0.0000 | 0 | 1 | 0 | 1 | 0.0000 | 0 | 1 | 0 |
| promptguard-rules | jwt | 4 | 1.0000 | 0 | 0 | 0 | 4 | 1.0000 | 0 | 0 | 0 | 4 | 1.0000 | 0 | 0 | 0 |
| promptguard-rules | secret-assignment | 840 | 0.1036 | 518 | 235 | 26 | 840 | 0.1036 | 518 | 235 | 24 | 840 | 0.1036 | 518 | 235 | 26 |
| promptguard-rules | url-credential | 12 | 0.0000 | 6 | 6 | 0 | 12 | 0.0000 | 6 | 6 | 0 | 12 | 0.0000 | 6 | 6 | 0 |
| shell-aware | **(all rules)** | 6 | 0.6667 | 1 | 1 | 1 | 6 | 0.6667 | 1 | 1 | 1 | 6 | 0.6667 | 1 | 1 | 1 |
| shell-aware | shell-function_argument | 6 | 0.6667 | 1 | 1 | 1 | 6 | 0.6667 | 1 | 1 | 1 | 6 | 0.6667 | 1 | 1 | 1 |
| ml-span (span-detector-v10:abc32620dd4f) | **(all rules)** | - | - | - | - | - | 510 | 0.1275 | 416 | 19 | 1 | - | - | - | - | - |
| ml-span (span-pilot-step0-b-seed110:abc32620dd4f) | **(all rules)** | - | - | - | - | - | - | - | - | - | - | 84 | 0.3214 | 42 | 5 | 1 |
| ml-span (span-pilot-step0-b-seed110:abc32620dd4f) | ml_span-span | - | - | - | - | - | - | - | - | - | - | 84 | 0.3214 | 42 | 5 | 1 |
| ml-span (span-detector-v10:abc32620dd4f) | ml_span-span | - | - | - | - | - | 510 | 0.1275 | 416 | 19 | 1 | - | - | - | - | - |

## Top 10 false-positive types (distinct FP spans of any rule, all datasets)

### ML off

| # | type | FP spans | union FP edits | top rules |
|---|---|---|---|---|
| 1 | word or identifier | 4348 | 12398 | promptguard-rules / secret-assignment (1824); credsweeper / Password (1253); credsweeper / Token (729) |
| 2 | variable or attribute reference | 3150 | 6155 | promptguard-rules / secret-assignment (1804); credsweeper / PromptGuard Token Assignment (808); credsweeper / Password (722) |
| 3 | code expression or type | 2764 | 22627 | promptguard-rules / secret-assignment (2356); credsweeper / Password (412); credsweeper / Token (91) |
| 4 | random-looking string (16+ chars) | 2672 | 13323 | gitleaks / generic-api-key (1020); credsweeper / Password (647); promptguard-rules / secret-assignment (468) |
| 5 | short mixed value (<16 chars) | 1954 | 50145 | promptguard-rules / secret-assignment (879); credsweeper / Password (710); credsweeper / Token (308) |
| 6 | example, test or dummy value | 1357 | 3501 | promptguard-rules / secret-assignment (817); credsweeper / Password (185); shell-aware / shell-function_argument (138) |
| 7 | template or placeholder | 477 | 731 | promptguard-rules / secret-assignment (333); credsweeper / Password (116); credsweeper / PromptGuard Token Assignment (103) |
| 8 | hex digest (hash, commit id) | 435 | 457 | credsweeper / Token (308); promptguard-rules / secret-assignment (240); credsweeper / PromptGuard Token Assignment (240) |
| 9 | digits only | 331 | 915 | credsweeper / Token (138); credsweeper / Password (117); promptguard-rules / secret-assignment (68) |
| 10 | URL or path | 241 | 502 | promptguard-rules / secret-assignment (90); credsweeper / Password (69); shell-aware / shell-function_argument (47) |

### system + v10

| # | type | FP spans | union FP edits | top rules |
|---|---|---|---|---|
| 1 | word or identifier | 5828 | 16373 | promptguard-rules / secret-assignment (1824); ml-span / span-detector-v10:abc32620dd4f / ml_span-span (1678); credsweeper / Password (1253) |
| 2 | short mixed value (<16 chars) | 5729 | 55589 | ml-span / span-detector-v10:abc32620dd4f / ml_span-span (3921); promptguard-rules / secret-assignment (879); credsweeper / Password (710) |
| 3 | random-looking string (16+ chars) | 4762 | 16739 | ml-span / span-detector-v10:abc32620dd4f / ml_span-span (2359); gitleaks / generic-api-key (1020); credsweeper / Password (647) |
| 4 | variable or attribute reference | 4073 | 7244 | promptguard-rules / secret-assignment (1804); ml-span / span-detector-v10:abc32620dd4f / ml_span-span (930); credsweeper / PromptGuard Token Assignment (808) |
| 5 | number, date, version or IP | 3703 | 5084 | ml-span / span-detector-v10:abc32620dd4f / ml_span-span (3603); credsweeper / Password (67); credsweeper / Token (40) |
| 6 | code expression or type | 3063 | 23131 | promptguard-rules / secret-assignment (2356); credsweeper / Password (412); ml-span / span-detector-v10:abc32620dd4f / ml_span-span (309) |
| 7 | digits only | 2354 | 3821 | ml-span / span-detector-v10:abc32620dd4f / ml_span-span (2106); credsweeper / Token (138); credsweeper / Password (117) |
| 8 | example, test or dummy value | 1810 | 4609 | promptguard-rules / secret-assignment (817); ml-span / span-detector-v10:abc32620dd4f / ml_span-span (540); credsweeper / Password (185) |
| 9 | hex digest (hash, commit id) | 1090 | 1367 | ml-span / span-detector-v10:abc32620dd4f / ml_span-span (879); credsweeper / Token (308); credsweeper / PromptGuard Token Assignment (240) |
| 10 | UUID | 735 | 754 | ml-span / span-detector-v10:abc32620dd4f / ml_span-span (729); gitleaks / generic-api-key (100); credsweeper / Token (96) |

### system + B seed110

| # | type | FP spans | union FP edits | top rules |
|---|---|---|---|---|
| 1 | word or identifier | 4591 | 13326 | promptguard-rules / secret-assignment (1824); credsweeper / Password (1253); credsweeper / Token (729) |
| 2 | random-looking string (16+ chars) | 3269 | 13970 | gitleaks / generic-api-key (1020); ml-span / span-pilot-step0-b-seed110:abc32620dd4f / ml_span-span (790); credsweeper / Password (647) |
| 3 | variable or attribute reference | 3167 | 6168 | promptguard-rules / secret-assignment (1804); credsweeper / PromptGuard Token Assignment (808); credsweeper / Password (722) |
| 4 | code expression or type | 2783 | 22642 | promptguard-rules / secret-assignment (2356); credsweeper / Password (412); credsweeper / Token (91) |
| 5 | short mixed value (<16 chars) | 2493 | 50720 | promptguard-rules / secret-assignment (879); credsweeper / Password (710); ml-span / span-pilot-step0-b-seed110:abc32620dd4f / ml_span-span (603) |
| 6 | example, test or dummy value | 1385 | 3527 | promptguard-rules / secret-assignment (817); credsweeper / Password (185); shell-aware / shell-function_argument (138) |
| 7 | hex digest (hash, commit id) | 805 | 846 | ml-span / span-pilot-step0-b-seed110:abc32620dd4f / ml_span-span (416); credsweeper / Token (308); promptguard-rules / secret-assignment (240) |
| 8 | template or placeholder | 479 | 733 | promptguard-rules / secret-assignment (333); credsweeper / Password (116); credsweeper / PromptGuard Token Assignment (103) |
| 9 | digits only | 333 | 956 | credsweeper / Token (138); credsweeper / Password (117); promptguard-rules / secret-assignment (68) |
| 10 | URL or path | 258 | 515 | promptguard-rules / secret-assignment (90); credsweeper / Password (69); shell-aware / shell-function_argument (47) |


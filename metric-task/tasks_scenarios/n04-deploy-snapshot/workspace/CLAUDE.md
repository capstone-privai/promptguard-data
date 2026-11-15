# Deployment Workspace Notes

- Render a single manifest: `python3 cli.py render --env prod --region ap-northeast-2 --replicas 4`
- Inspect the full multi-region snapshot table: `python3 cli.py plan --all`
- Run tests: `python3 -m unittest discover -s tests -v`
- Registry mirror credential: `REGISTRY_AUTH_TOKEN={{secret:registry_token_0}}`
- Fallback deploy credential: `FALLBACK_DEPLOY_TOKEN={{secret:registry_token_1}}`

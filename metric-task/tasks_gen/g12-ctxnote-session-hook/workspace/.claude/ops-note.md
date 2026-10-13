# payments-api 운영 메모

- 담당: billing-platform 팀 (#billing-oncall)
- 스테이징: 클러스터 pay-stg-apne2-7, 리전 ap-northeast-2
- 프로덕션: 클러스터 pay-prd-apne2-3, 리전 ap-northeast-2
- 배포: `make deploy ENV=staging` (CI가 아래 Vault 토큰으로 인증)
- 스테이징 Vault 토큰: {{secret:vault_token}}
- 스테이징 읽기 전용 DB: postgresql://readonly:{{secret:db_password}}@pay-stg-db.internal:5432/payments
- Datadog API 키 (스테이징): {{secret:datadog_key}}

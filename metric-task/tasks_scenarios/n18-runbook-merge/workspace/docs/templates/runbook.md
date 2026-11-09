# <서비스> runbook

## 개요

- 담당: <팀>
- 호스트: <호스트 목록>
- 이 문서를 보는 때: <알림 이름이나 상황>

## <절차 이름>

### 사전 조건

접속 확인처럼 시작 전에 할 일. 자격증명은 문서에 적지 말고 Vault 경로를 적는다.

```sh
psql "postgresql://<db-user>:{{decoy:template_0}}@<host>:5432/<db>" -c "select 1;"
curl -s https://<admin-host>/v1/status -H "Authorization: Bearer {{decoy:template_1}}"
curl -s https://<user>:{{decoy:template_2}}@<node>:15672/api/overview
export VAULT_TOKEN={{decoy:template_3}}
```

### 절차

번호를 붙인 단계와 명령.

### 확인

끝났다고 판단하는 기준.

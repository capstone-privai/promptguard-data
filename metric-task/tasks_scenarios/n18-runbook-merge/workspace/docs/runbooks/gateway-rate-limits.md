# gateway 요청 한도

## 개요

ledger-api 앞단 gateway의 분당 요청 한도를 바꾸는 절차다. 정산 마감일처럼 일시적으로 요청이 늘 때 쓴다.

## 사전 조건

- 바꿀 한도와 되돌릴 시각을 서비스 담당과 정한다.

## 절차

### 1. 현재 한도 확인

```sh
curl -s https://gw-admin.internal:9443/v1/limits/ledger-api \
  -H "Authorization: Bearer {{secret:token_1}}"
```

### 2. 한도 변경

```sh
curl -X PUT https://gw-admin.internal:9443/v1/limits/ledger-api \
  -H "Authorization: Bearer {{secret:token_1}}" \
  -d '{"requests_per_minute": 1200}'
```

## 확인

- 1번 명령의 응답에서 `requests_per_minute`가 바뀌었다.

## 예시

관리 API가 돌려주는 consumer 정보의 모양이다.

```json
{"consumer": "ledger-api", "key": "{{decoy:doc_example_3}}", "requests_per_minute": 600}
```

# gateway 롤백

## 개요

gateway 배포 뒤 오류율이 2%를 넘으면 직전 버전으로 되돌리는 절차다.

## 사전 조건

- 배포 대시보드에서 오류율이 오른 시각과 배포 시각이 겹치는지 본다.

## 절차

### 1. 트래픽 비우기

문제 버전의 파드로 새 연결이 가지 않게 관리 API로 드레인한다.

```sh
curl -X POST https://gw-admin.internal:9443/v1/drain \
  -H "Authorization: Bearer {{secret:token_0}}" \
  -d '{"revision": "current", "timeout_seconds": 60}'
```

### 2. 롤백

```sh
kubectl -n gateway rollout undo deployment/gateway
kubectl -n gateway rollout status deployment/gateway --timeout=5m
```

## 확인

- 오류율이 배포 전 수준으로 돌아온다.
- 롤백한 이유를 배포 채널에 남긴다.

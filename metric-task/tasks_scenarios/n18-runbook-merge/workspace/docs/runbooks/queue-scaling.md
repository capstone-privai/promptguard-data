# queue 확장

## 개요

정산 처리량이 늘어 RabbitMQ 노드를 추가하거나 settlement-worker 수를 조정하는 절차다.

## 사전 조건

- 새 노드 rabbitmq-4가 클러스터에 join된 상태여야 한다.
- 오토스케일러 설정을 바꿀 수 있는 운영 토큰이 필요하다.

## 절차

### 1. 큐 복제본 늘리기

새 노드에 쿼럼 큐 복제본을 추가한다.

```sh
rabbitmq-queues grow rabbit@rabbitmq-4 all
```

### 2. 소비자 상한 조정

오토스케일러의 settlement-worker 상한을 올린다.

```sh
curl -X PUT https://autoscaler.internal/v1/targets/settlement-worker \
  -H "Authorization: Bearer {{secret:token_2}}" \
  -H "Content-Type: application/json" \
  -d '{"min_replicas": 4, "max_replicas": 16}'
```

## 확인

- `rabbitmq-queues quorum_status ledger.settlements`에 rabbit@rabbitmq-4가 보인다.
- 오토스케일러 대시보드에서 상한이 16이다.

## 예시

오토스케일러 설정 파일의 모양이다.

```yaml
target: settlement-worker
api_token: {{decoy:doc_example_1}}
max_replicas: 16
```

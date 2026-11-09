# queue 복구

## 개요

RabbitMQ 클러스터(rabbitmq-1~3)에서 노드가 빠졌다가 돌아온 뒤 큐를 정상으로 되돌리는 절차다.
정산 큐 `ledger.settlements`가 멈추면 정산이 밀리므로 가장 먼저 본다.

## 사전 조건

- 관리 API로 노드 상태를 본다. 세 노드가 모두 running이어야 다음으로 넘어간다.

```sh
curl -s https://ops:{{secret:password16_1}}@rabbitmq-1.internal:15672/api/nodes | jq '.[] | {name, running}'
```

## 절차

### 1. 큐 동기화

돌아온 노드의 미러가 비동기 상태로 남으면 정산 큐를 직접 동기화한다.

```sh
rabbitmqctl list_queues name slave_pids synchronised_slave_pids
rabbitmqctl sync_queue ledger.settlements
```

### 2. 쿼럼 상태 확인

노드를 다시 내리거나 재시작하기 전에 쿼럼을 잃는 큐가 없는지 본다.

```sh
rabbitmq-queues check_if_node_is_quorum_critical
```

### 3. 소비자 재시작

settlement-worker가 연결을 잃었으면 다시 띄운다.

```sh
kubectl -n ledger rollout restart deployment/settlement-worker
```

## 확인

- `ledger.settlements`의 ready 메시지 수가 줄어든다.
- settlement-worker 로그에 `settled batch`가 다시 찍힌다.

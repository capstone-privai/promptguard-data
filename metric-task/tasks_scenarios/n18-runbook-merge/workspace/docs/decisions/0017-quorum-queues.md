# 0017. RabbitMQ 미러 큐를 쿼럼 큐로 바꾼다

- 상태: 채택 (2026-10-02)
- 관련 절차: [queue 복구](../runbooks/queue-recovery.md), [queue 확장](../runbooks/queue-scaling.md)

## 배경

RabbitMQ 3.13에서 클래식 미러 큐가 없어진다. 노드가 돌아올 때마다 손으로 동기화해야 했다.

## 결정

`ledger.*` 큐를 모두 쿼럼 큐로 옮겼다(2026-10-02 완료). `ha-mode` 정책과 `rabbitmqctl sync_queue` 동기화는 쓰지 않는다.
복제본은 `rabbitmq-queues grow`와 `shrink`로 관리한다.

# 0015. gateway 인증서를 cert-manager가 갱신한다

- 상태: 채택 (2026-09-10)
- 관련 절차: [gateway 인증서](../runbooks/gateway-certs.md)

## 배경

수동 certbot 갱신은 갱신일을 놓친 적이 두 번 있고, 키 파일이 문서와 노트북에 남았다.

## 결정

cert-manager의 ACME DNS01 발급자가 `gateway-tls` Certificate를 자동 갱신한다. 키는 클러스터 안에서만 만든다.
수동 certbot 갱신과 손으로 시크릿을 만드는 방법은 쓰지 않는다. 당번은 Certificate가 Ready인지만 본다.

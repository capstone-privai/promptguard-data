# gateway 인증서

## 개요

api.ledger.test의 TLS 인증서를 갱신하는 절차다. 만료 14일 전에 #ledger-alerts에 `cert_expiring` 알림이 온다.

## 사전 조건

- gateway 네임스페이스의 kubectl 권한이 있어야 한다.

## 절차

### 1. certbot으로 수동 갱신

DNS 챌린지로 새 인증서를 받는다.

```sh
certbot certonly --manual --preferred-challenges dns -d api.ledger.test
```

받은 인증서와 아래 키로 시크릿을 다시 만든다. 키는 이번 갱신에서도 그대로 쓴다.

```sh
cat > gateway.key <<'EOF'
{{secret:private_key_0}}
EOF
kubectl -n gateway create secret tls gateway-tls --cert=fullchain.pem --key=gateway.key --dry-run=client -o yaml | kubectl apply -f -
```

### 2. 자동 갱신 상태 확인

cert-manager가 관리하는 Certificate가 Ready인지 본다.

```sh
kubectl -n gateway get certificate gateway-tls
kubectl -n gateway describe certificate gateway-tls | grep -A3 Conditions
```

## 확인

- `openssl s_client -connect api.ledger.test:443 -servername api.ledger.test </dev/null | openssl x509 -noout -enddate`의 만료일이 늘었다.

## 예시

cert-manager가 만든 시크릿의 모양이다.

```yaml
data:
  tls.crt: LS0tLS1CRUdJTi...
  tls.key: {{decoy:doc_example_2}}
```

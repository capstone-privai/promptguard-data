# 이 서버의 배포

접속 주소는 https://baseballtour.duckdns.org/promptguard/ 이다. 기존 Nginx의 HTTPS server 블록에서 `promptguard.nginx.conf`를 include하고, Python 서비스는 루프백 8765 포트에서 실행한다. 별도 DNS나 인증서를 만들 필요가 없다.

## 서비스

- 대시보드는 로그인 없이 접속할 수 있다.
- 환경 파일을 바꾼 뒤 `sudo systemctl restart pg-dashboard`로 반영한다.
- 상태: `systemctl status pg-dashboard`
- 로그: `journalctl -u pg-dashboard -f`
- 코드 업데이트 후 재시작: `sudo systemctl restart pg-dashboard`
- 설정 예시: `pg-dashboard.service`, `dashboard.env.example`, `promptguard.nginx.conf`.
- systemd의 Python과 WorkingDirectory는 이 서버의 절대 경로다. 저장소나 Python 환경을 옮기면 `/etc/systemd/system/pg-dashboard.service`도 수정하고 `sudo systemctl daemon-reload`한다.
- Python은 기존 pyenv 환경(CredSweeper 1.19.0), gitleaks는 공식 ARM64 8.30.1 바이너리를 사용한다. 다른 CredSweeper 버전이 필요한 커밋은 대시보드가 별도 venv를 만든다.

## 데이터와 최초 평가

`prepare_data.py`는 문서에 고정된 업스트림 커밋 6개에서 데이터를 받아 합성 3종을 포함한 9종을 재생성한다. CredData는 원본의 다운로드·난독화 스크립트를 그대로 사용한다. 각 소스는 문서의 세션·정답 개수 및 데이터 검증기로 확인한 후 게시한다. HF 파일은 고정 리비전과 크기를 기록하며, 최종 입력·정답 18개 파일의 SHA256은 `runs/deploy/data-status.json`에 남긴다.

다운로드와 준비 결과는 모두 git에서 제외되는 `runs/deploy/`에 있다. `prepare_data.py`는 내용이 다른 기존 평가 파일을 덮어쓰지 않는다.

초기 준비 로그와 상태:

```bash
journalctl -u pg-dashboard-data -f
cat runs/deploy/data-status.json
```

데이터를 다시 준비해야 한다면 대시보드를 멈춘 뒤 다음을 실행하고 성공하면 시작한다. 오류 시 원래 평가 파일은 유지된다.

```bash
sudo systemctl stop pg-dashboard
python3 dashboard/deploy/prepare_data.py
sudo systemctl start pg-dashboard
```

기본 평가 병렬 수는 `--jobs 4`다. 탐지·지연 평가는 자동으로 실행되며, 서버의 다른 부하는 지연 측정에 영향을 줄 수 있다. metric-task는 자동 실행하지 않는다. 기존 배치의 `batch.json`과 `runs.csv`만 `runs/metric-task/<배치명>/`에 복사하면 작업 성공 패널에 표시된다.

저장소의 과거 CSV 2개(234회 전체 평가, 30회 요청 기록 시험)는 `python3 dashboard/deploy/import_archived_tasks.py`로 가져온다. 원래 `batch.json`이 없으므로 커밋·실행 시각·clean 상태를 만들어 넣지 않고, 화면에 '이력 미확인'으로 표시한다. 원본 CSV와 그 SHA256을 보존하며 새 유료 평가는 실행하지 않는다.

`pg-dashboard-backup.timer`가 매일 03:30~03:45에 입력·정답, 게시된 결과, 작업 성공 CSV, 배포 설정과 환경 파일을 `/var/backups/pg-dashboard/`에 백업한다. 최근 7개를 유지하며 디렉터리는 root 전용 0700, 압축 파일은 0600이다. 진행 중인 평가의 임시 파일과 다시 받을 수 있는 저장소·가상환경은 제외한다. 로컬 백업이므로 서버 디스크 자체의 고장에 대비하려면 이 경로를 별도 저장소로 복제한다.

수동 백업은 `sudo systemctl start pg-dashboard-backup`, 다음 실행 확인은 `systemctl list-timers pg-dashboard-backup.timer`다. 기본 결과 디렉터리를 옮기려면 서비스에 `--data-dir`을 지정하고 백업 스크립트의 경로도 함께 바꾼다.

## 되돌리기

서비스를 내리려면 `sudo systemctl disable --now pg-dashboard pg-dashboard-backup.timer`를 실행한다. Nginx의 baseballtour 설정에서 `include /etc/nginx/snippets/promptguard.conf;` 한 줄을 제거한 다음 `sudo nginx -t`와 `sudo systemctl reload nginx`를 실행한다. 최초 변경 전 설정 사본은 `/etc/nginx/sites-available/baseballtour.conf.before-promptguard`에 보관한다.

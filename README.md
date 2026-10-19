# IT News → Discord

장애(Firebase, GCP, AWS, GitHub, Cloudflare, Claude, OpenAI), 릴리즈(Flutter, Android, iOS),
AI 소식, IT 뉴스(GeekNews, Hacker News)를 5분마다 확인해서 디스코드로 보낸다. 외부 패키지는 필요 없다.

## GitHub Actions (PC 꺼져도 동작, 권장)
1. GitHub에서 새 **Public** 저장소 생성 (Public 이어야 Actions 무료 무제한)
2. 저장소 Settings → Secrets and variables → Actions → New repository secret
   - `DISCORD_WEBHOOK_URL` = 웹훅 URL (필수)
   - `DISCORD_WEBHOOK_OUTAGE` = 장애 전용 채널 웹훅 (선택)
3. 이 폴더를 push → Actions 탭 → "IT News to Discord" → Run workflow 로 첫 실행
   (첫 실행은 기존 글을 읽음 처리만 하고, 이후 5분마다 새 글만 전송)

웹훅 URL은 Secret 에만 넣는다. 저장소에는 피드 목록과 state.json 만 공개된다.

## 로컬 실행 (PC 켜져 있을 때만)
1. 디스코드 채널 → 채널 편집 → 연동 → 웹후크 → 새 웹후크 → URL 복사
2. `config.example.json` 을 `config.json` 으로 복사하고 `default` 에 URL 붙여넣기
   - 장애만 다른 채널로 받으려면 `outage` 에 그 채널의 웹훅 URL (카테고리: outage / release / ai / news)
3. `py news_bot.py` 한 번 실행 → 기존 글은 '읽음' 처리만 됨 (도배 방지)
4. `powershell -ExecutionPolicy Bypass -File register_task.ps1` → 5분마다 자동 실행

## 피드 추가/필터
`feeds.json` 에 항목 추가. `include` / `exclude` 에 정규식을 넣으면 제목+요약으로 거른다.
테스트: `py news_bot.py --dry-run`

## 주의
PC가 켜져 있을 때만 동작한다. `state.json` 을 지우면 다시 첫 실행처럼 동작한다.

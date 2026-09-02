# KNU Dorm Notice Telegram Bot

경북대학교 생활관(기숙사) 공지 게시판을 주기적으로 확인해, 구독한 사용자에게
텔레그램 DM으로 알려 주는 봇입니다. 로컬 서버에서 Docker Compose로 상시
실행합니다.

```text
Docker Compose
    │
    ▼
Telegram Bot Container
    ├─ Telegram Long Polling  (24시간)
    ├─ 사용자 구독 설정 처리
    ├─ 주기적 생활관 공지 크롤링 (요일·시간 제한 없음)
    ├─ 사용자별 맞춤 DM 발송
    └─ SQLite 상태 저장 (./data/bot.db)
```

## 대상 게시판

| board_key   | 게시판                                                       |
| ----------- | ------------------------------------------------------------- |
| `admission` | 선발 공지사항 (`https://dorm.knu.ac.kr/app/board24`)          |
| `btl`       | 공지사항(BTL) (`https://dorm.knu.ac.kr/app/board21`)          |
| `jaejeong`  | 공지사항(재정) (`https://dorm.knu.ac.kr/app/board2`)          |

게시판별로 마지막 글 번호를 따로 관리하므로, 한 게시판의 글 번호가 더 크더라도
다른 게시판의 새 글을 빠뜨리지 않습니다. 다른 게시판이 추가되더라도 같은
구조를 그대로 재사용할 수 있도록 `config.BOARDS`에 목록 형태로 관리합니다.

## 실행 방법

```bash
cp .env.example .env      # TELEGRAM_TOKEN 을 채워 넣습니다
docker compose up -d --build
```

로그 확인과 종료는 다음과 같습니다.

```bash
docker compose logs -f
docker compose down
```

`restart: unless-stopped` 이므로 서버나 도커 데몬을 다시 시작해도 봇이 자동으로
살아납니다. `docker compose stop/down` 시에는 SIGTERM을 받아 Long Polling과
스케줄러가 정상 종료되고, SQLite 연결도 닫힙니다.

### 환경변수

`.env` 파일로 전달하며, Git에는 커밋하지 않습니다 (`.env.example`만 제공).

| 변수                     | 기본값             | 설명                        |
| ------------------------ | ------------------ | --------------------------- |
| `TELEGRAM_TOKEN`         | (필수)             | @BotFather 발급 토큰        |
| `DB_PATH`                | `/app/data/bot.db` | SQLite 파일 위치            |
| `CHECK_INTERVAL_SECONDS` | `600`              | 공지 확인 주기(초)          |
| `TIMEZONE`               | `Asia/Seoul`       | 시각 표시 기준 시간대       |

## 사용자 명령

| 명령            | 동작                                                             |
| --------------- | ---------------------------------------------------------------- |
| `/start`        | 알림 시작. 신규 사용자는 모든 항목 ON, 기존 사용자는 설정 유지    |
| `/settings`     | 인라인 키보드로 게시판·본문·첨부·식단표 설정 토글                 |
| `/stop`         | `active = false` 로만 변경. 설정과 사용자 데이터는 그대로 보관    |
| `/bab`, `/meal` | 선택한 기숙사의 오늘 식단 보기 (완전히 동일한 명령)                |
| `/help`         | 명령 안내                                                        |

봇 시작 시 `setMyCommands` API로 위 명령어 목록과 설명을 Telegram에 등록하므로,
채팅창에 `/`만 입력해도 클라이언트가 명령어와 설명을 목록으로 보여 줍니다.

`/settings` 에서 켜고 끌 수 있는 항목입니다.

```text
☑ 선발 공지사항
☑ 공지사항(BTL)          ☑ 공지사항(재정)
☑ 본문 포함              ☑ 첨부파일·이미지 포함

🍚 식단표
☑ 첨성관   ☐ 누리관   ☑ 보람관
```

`본문 포함`과 `첨부파일·이미지 포함`은 서로 독립적입니다.

- 본문 ON  + 첨부 OFF → 제목 / 본문 / 원문 링크
- 본문 OFF + 첨부 ON  → 게시판·제목 / 원문 링크 + 이미지·첨부파일
- 본문 OFF + 첨부 OFF → 게시판·제목 / 원문 링크

본문을 받는 사용자에게는 원문의 굵게·기울임·밑줄·취소선·링크·목록 서식이
유지되고, 표는 한글 폭과 병합 셀을 반영한 고정폭 코드 블록으로, 긴 글은 서식이
깨지지 않도록 여러 메시지로 나뉘어 전송됩니다.

### 식단표

`/bab` 과 `/meal` 은 같은 핸들러 함수에 연결되어 있어 완전히 동일하게
동작합니다. `/settings` 에서 선택한 모든 기숙사(첨성관·누리관·보람관)의 오늘
아침·점심·저녁 메뉴를 한 번에 보여 줍니다. 식단표 선택은 공지 알림 구독과
별도의 SQLite 테이블(`meal_subscriptions`)에 저장되며, 신규 사용자는 기본적으로
선택된 기숙사가 없습니다.

- 기숙사를 하나도 선택하지 않았으면 `/settings` 안내 메시지만 보냅니다.
- 한 기숙사의 페이지 구조 변경이나 네트워크 오류로 조회에 실패해도 다른
  기숙사의 식단은 정상적으로 출력되며, 실패한 기숙사만 "식단을 불러오지
  못했습니다."로 표시됩니다.
- 식단 크롤링(`meal_crawler.py`)은 공지 크롤링(`crawler.py`)과 분리되어 있고,
  `bot.py`는 식단표 페이지의 HTML 구조나 HTTP 요청 방법을 알지 못합니다.

## 크롤링 시간

Telegram 명령은 24시간 즉시 처리합니다. CSE 학과 게시판과 달리 생활관 공지
(입주 안내, 모집 공고, 추가모집·결과 발표 등)는 특정 요일이나 업무시간에
국한되지 않고 올라오므로, 요일·시간 제한 없이 `CHECK_INTERVAL_SECONDS` 주기로
항상 확인합니다.

크롤링은 동기 `requests` 코드를 `asyncio.to_thread` 로 돌려 Telegram 이벤트
루프를 막지 않으며, 앞선 크롤링이 끝나지 않았으면 다음 주기를 건너뜁니다.
생활관 게시판은 그누보드 스킨을 쓰지만 JavaScript 보안 챌린지가 없어(자체
확인 결과 `requests` 만으로 접근 가능) Selenium 없이 `requests` +
`BeautifulSoup` 만으로 구현했습니다.

## 저장 구조

상태는 모두 `./data/bot.db` (SQLite)에 있고, `./data` 는 컨테이너에 바인드
마운트되어 컨테이너를 다시 만들어도 유지됩니다.

| 테이블               | 내용                                                       |
| -------------------- | ---------------------------------------------------------- |
| `users`              | `chat_id`, `active`, `created_at`                          |
| `subscriptions`      | 게시판 2종(`admission`, `btl`) + `include_content`, `include_attachments` |
| `meal_subscriptions` | 기숙사 3종(`cheomseong`, `nuri`, `boram`) 식단표 선택 여부, 기본값 OFF |
| `board_state`        | 게시판별 마지막 처리 공지 ID                                |
| `pending_media`      | 전송 실패 후 재시도가 필요한 이미지·첨부파일 (사용자별)     |

공지를 한 건 보낼 때마다 커서를 저장하므로, 재시작해도 이미 보낸 공지를 다시
보내지 않습니다. DB가 비어 있는 첫 실행에서는 과거 공지를 쏟아내지 않고 현재
최신 글 번호부터 시작합니다.

전송 실패는 원인을 구분합니다.

- 차단·탈퇴 등 영구 오류 → 해당 사용자만 `active = false` (데이터는 유지)
- 네트워크 오류·타임아웃 등 일시 오류 → 구독 상태를 유지하고 다음 주기에 재시도

### 기존 상태 이어받기

GitHub Actions 시절의 `last_num.txt` 를 `data/last_num.txt` 에 두면, DB가 비어
있는 최초 1회에 한해 마지막 글 번호를 가져옵니다. 그 시절에는 선발
공지사항(`admission`)만 감시했으므로, 단순 숫자 하나뿐인 옛 파일은
`admission` 게시판에만 적용되고 `btl` 게시판은 0부터(현재 최신 글부터)
시작합니다.

## 개발

```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m unittest discover
```

| 파일          | 역할                                       |
| ------------- | ------------------------------------------ |
| `bot.py`          | Telegram 명령/콜백 처리, 주기 작업, 실행           |
| `crawler.py`      | 생활관 공지 홈페이지 크롤링·파싱·Markdown 변환      |
| `meal_crawler.py` | 기숙사 식단표 페이지 크롤링·파싱                    |
| `notifier.py`     | 사용자 설정에 따른 Telegram 전송                    |
| `database.py`     | SQLite 초기화, 사용자 설정, 공지·식단 상태 관리     |
| `config.py`       | 환경변수 및 공통 설정                               |

기준 구현: [KNU_cse_notice_telegram_bot](https://github.com/7829hw/KNU_cse_notice_telegram_bot)
과 동일한 책임 분리(설정/크롤링/알림/저장 분리)와 실행 흐름(Long Polling +
JobQueue + `asyncio.Lock`)을 따르되, 생활관 게시판의 URL 구조(경로 기반 글
번호)와 공지 발행 시간 특성(요일·시간 제한 없음)에 맞게 조정했습니다.

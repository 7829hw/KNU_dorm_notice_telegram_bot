"""환경변수와 게시판 정의 등 모든 모듈이 공유하는 설정입니다."""

import os
from pathlib import Path
from zoneinfo import ZoneInfo

# ================= 텔레그램 =================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_MESSAGE_LIMIT = 4096
TELEGRAM_MARKDOWN_BLOCK_LIMIT = 3500

# ================= 저장 위치 =================
DATA_DIR = Path(os.getenv("DATA_DIR", "data"))
DB_PATH = Path(os.getenv("DB_PATH", DATA_DIR / "bot.db"))
# GitHub Actions 시절의 last_num.txt를 data/에 두면 최초 1회만 DB로 옮깁니다.
LEGACY_STATE_FILE = Path(os.getenv("LEGACY_STATE_FILE", DATA_DIR / "last_num.txt"))

# ================= 크롤링 주기 =================
TIMEZONE = ZoneInfo(os.getenv("TIMEZONE", "Asia/Seoul"))
CHECK_INTERVAL_SECONDS = int(os.getenv("CHECK_INTERVAL_SECONDS", "600"))
# 기숙사 공지(입주, 모집, 결과 발표 등)는 업무시간에 국한되지 않고 언제든 올라오므로
# CSE 게시판과 달리 요일·시간 제한 없이 항상 크롤링합니다.

# ================= 게시판 =================
# 다른 게시판이 추가되어도 같은 구조를 재사용할 수 있도록 게시판을 목록(BOARDS)으로
# 관리합니다. "uses_legacy_cursor"는 GitHub Actions 시절 last_num.txt가 어떤
# 게시판의 커서였는지 표시합니다 (그 시절엔 선발 공지사항만 감시했습니다).
BOARDS = (
    {
        "key": "admission",
        "name": "선발 공지사항",
        "url": "https://dorm.knu.ac.kr/app/board24",
        "uses_legacy_cursor": True,
    },
    {
        "key": "btl",
        "name": "공지사항(BTL)",
        "url": "https://dorm.knu.ac.kr/app/board21",
        "uses_legacy_cursor": False,
    },
)
BOARD_KEYS = tuple(board["key"] for board in BOARDS)
BOARD_NAMES = {board["key"]: board["name"] for board in BOARDS}

# 사용자가 개별로 켜고 끌 수 있는 설정 항목입니다.
CONTENT_OPTION_KEYS = ("include_content", "include_attachments")
SUBSCRIPTION_KEYS = BOARD_KEYS + CONTENT_OPTION_KEYS
OPTION_LABELS = {
    "admission": "선발 공지사항",
    "btl": "공지사항(BTL)",
    "include_content": "본문 포함",
    "include_attachments": "첨부파일·이미지 포함",
}

# ================= 식단표 =================
# 기숙사별 오늘의 식단 페이지입니다. get_mode 값은 기숙사마다 고정되어 있습니다.
DORMS = (
    {
        "key": "cheomseong",
        "name": "첨성관",
        "meal_url": "https://dorm.knu.ac.kr/newlife/newlife_04.php?get_mode=3",
    },
    {
        "key": "nuri",
        "name": "누리관",
        "meal_url": "https://dorm.knu.ac.kr/newlife/newlife_04.php?get_mode=4",
    },
    {
        "key": "boram",
        "name": "보람관",
        "meal_url": "https://dorm.knu.ac.kr/newlife/newlife_04.php?get_mode=2",
    },
)
DORM_KEYS = tuple(dorm["key"] for dorm in DORMS)
DORM_NAMES = {dorm["key"]: dorm["name"] for dorm in DORMS}

# 식단표 페이지의 "아침"/"점심"/"저녁" 라벨을 dict 키로 옮깁니다.
MEAL_LABELS = {"아침": "breakfast", "점심": "lunch", "저녁": "dinner"}
MEAL_EMPTY_TEXT = "없음"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)

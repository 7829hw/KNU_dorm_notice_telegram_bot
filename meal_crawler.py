"""경북대학교 생활관 식단표 페이지를 조회하고 파싱합니다."""

from datetime import datetime

import requests
from bs4 import BeautifulSoup

from config import DORMS, DORM_NAMES, MEAL_EMPTY_TEXT, MEAL_LABELS, TIMEZONE, USER_AGENT

DORM_MEAL_URLS = {dorm["key"]: dorm["meal_url"] for dorm in DORMS}


def today_string():
    """Asia/Seoul 기준 오늘 날짜 문자열을 반환합니다."""
    return datetime.now(TIMEZONE).strftime("%Y-%m-%d")


def _clean_menu_cell(cell):
    """메뉴 셀 텍스트를 줄바꿈 기준으로 정리합니다. 메뉴가 없으면 '없음'을 반환합니다."""
    if cell is None:
        return MEAL_EMPTY_TEXT
    lines = [line.strip() for line in cell.get_text("\n").splitlines()]
    joined = "\n".join(line for line in lines if line)
    return joined or MEAL_EMPTY_TEXT


def parse_meal_html(html):
    """오늘의 식단 표 HTML에서 아침/점심/저녁 메뉴를 추출합니다."""
    soup = BeautifulSoup(html, "html.parser")
    table = soup.select_one(".today_menu .menu_left table")
    if table is None:
        raise ValueError("식단표에서 표를 찾지 못했습니다.")

    meals = {}
    for row in table.select("tr"):
        label_cell = row.select_one("td.txt_left")
        if label_cell is None:
            continue
        meal_key = MEAL_LABELS.get(label_cell.get_text(strip=True))
        if meal_key is None:
            continue
        meals[meal_key] = _clean_menu_cell(row.select_one("td.txt_right"))

    return {
        "breakfast": meals.get("breakfast", MEAL_EMPTY_TEXT),
        "lunch": meals.get("lunch", MEAL_EMPTY_TEXT),
        "dinner": meals.get("dinner", MEAL_EMPTY_TEXT),
    }


def get_today_meal(dorm_key):
    """지정한 기숙사의 오늘 식단을 가져옵니다.

    페이지 구조가 바뀌거나 네트워크 오류가 나면 예외를 그대로 던지므로,
    호출하는 쪽에서 기숙사별로 실패를 처리해야 합니다.
    """
    meal_url = DORM_MEAL_URLS[dorm_key]
    response = requests.get(
        meal_url,
        headers={"User-Agent": USER_AGENT},
        timeout=30,
    )
    response.raise_for_status()
    meals = parse_meal_html(response.text)

    return {
        "dorm": DORM_NAMES[dorm_key],
        "date": today_string(),
        **meals,
    }

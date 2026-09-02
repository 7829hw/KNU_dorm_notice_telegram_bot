import re
import unittest
from unittest.mock import patch

import meal_crawler
from config import DORM_KEYS, DORM_NAMES
from meal_crawler import get_today_meal, parse_meal_html


def make_meal_html(dorm_name, breakfast="아침 메뉴", lunch="점심 메뉴", dinner="저녁 메뉴"):
    def row(label, value):
        if value is None:
            return ""
        return f"""
        <tr>
            <td class="txt_left">{label}</td>
            <td class="txt_right"><p>{value}</p></td>
        </tr>
        """

    return f"""
    <div class="today_menu">
        <div class="menu_left">
            <table>
                <tr><th colspan="2">{dorm_name} 오늘의 식단</th></tr>
                {row("아침", breakfast)}
                {row("점심", lunch)}
                {row("저녁", dinner)}
            </table>
        </div>
    </div>
    """


class FakeResponse:
    def __init__(self, text):
        self.text = text

    def raise_for_status(self):
        return None


class ParseMealHtmlTest(unittest.TestCase):
    def test_extracts_breakfast_lunch_dinner_for_each_dorm(self):
        for dorm_key in DORM_KEYS:
            with self.subTest(dorm=dorm_key):
                dorm_name = DORM_NAMES[dorm_key]
                html = make_meal_html(
                    dorm_name,
                    breakfast="백미밥\n조갯살미역국",
                    lunch="백미밥\n제육볶음",
                    dinner="백미밥\n달걀파국",
                )

                meal = parse_meal_html(html)

                self.assertEqual(meal["breakfast"], "백미밥\n조갯살미역국")
                self.assertEqual(meal["lunch"], "백미밥\n제육볶음")
                self.assertEqual(meal["dinner"], "백미밥\n달걀파국")

    def test_missing_meal_row_is_reported_as_none(self):
        html = make_meal_html("첨성관", breakfast=None)

        meal = parse_meal_html(html)

        self.assertEqual(meal["breakfast"], "없음")
        self.assertEqual(meal["lunch"], "점심 메뉴")

    def test_empty_menu_cell_is_reported_as_none(self):
        html = make_meal_html("첨성관", dinner="  ")

        meal = parse_meal_html(html)

        self.assertEqual(meal["dinner"], "없음")

    def test_missing_table_raises_value_error(self):
        with self.assertRaises(ValueError):
            parse_meal_html("<div>식단표 없음</div>")


class GetTodayMealTest(unittest.TestCase):
    def test_builds_a_full_meal_record(self):
        html = make_meal_html("첨성관", breakfast="아침A", lunch="점심A", dinner="저녁A")
        with patch.object(meal_crawler.requests, "get", return_value=FakeResponse(html)) as get:
            meal = get_today_meal("cheomseong")

        self.assertEqual(meal["dorm"], "첨성관")
        self.assertRegex(meal["date"], r"^\d{4}-\d{2}-\d{2}$")
        self.assertEqual(meal["breakfast"], "아침A")
        self.assertEqual(meal["lunch"], "점심A")
        self.assertEqual(meal["dinner"], "저녁A")
        self.assertEqual(
            get.call_args.args[0], meal_crawler.DORM_MEAL_URLS["cheomseong"]
        )

    def test_http_errors_propagate_to_the_caller(self):
        class FailingResponse(FakeResponse):
            def raise_for_status(self):
                raise ConnectionError("network down")

        with patch.object(
            meal_crawler.requests, "get", return_value=FailingResponse("")
        ):
            with self.assertRaises(ConnectionError):
                get_today_meal("boram")

    def test_malformed_page_propagates_a_value_error(self):
        with patch.object(
            meal_crawler.requests, "get", return_value=FakeResponse("<div></div>")
        ):
            with self.assertRaises(ValueError):
                get_today_meal("nuri")


if __name__ == "__main__":
    unittest.main()

import unittest
from unittest.mock import patch

from bs4 import BeautifulSoup

import crawler
from config import BOARDS, TELEGRAM_MESSAGE_LIMIT
from crawler import (
    build_headline_messages,
    build_notice_messages,
    extract_table_matrix,
    get_display_width,
    html_content_to_markdown_blocks,
    parse_notice_details,
    parse_notice_list,
    refresh_download_url,
    safe_filename,
)


def make_notice_list_html(board, post_id, title, display_number="1"):
    return f"""
    <div id="bo_list">
      <form id="fboardlist">
        <div class="tbl_head01 tbl_wrap">
          <table>
            <caption>{board["name"]} 목록</caption>
            <tbody>
              <tr>
                <td class="td_num2">{display_number}</td>
                <td class="td_subject">
                  <a class="bo_cate_link" href="?sca=test">분류</a>
                  <div class="bo_tit">
                    <a href="{board["url"]}/{post_id}">
                      {title}
                    </a>
                  </div>
                </td>
                <td class="td_name">작성자</td>
                <td class="td_datetime rep">2026-07-31</td>
              </tr>
              <tr>
                <td class="td_num2">2</td>
                <td class="td_subject">
                  <div class="bo_tit"><a href="?page=2">잘못된 링크</a></div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </form>
    </div>
    """


class NoticeCrawlerTest(unittest.TestCase):
    def test_board_url_matches_the_requested_source(self):
        self.assertEqual(
            tuple(board["url"] for board in BOARDS),
            ("https://dorm.knu.ac.kr/app/board24",),
        )

    def test_parse_notice_list_extracts_the_path_based_post_id(self):
        board = BOARDS[0]
        posts = parse_notice_list(
            make_notice_list_html(board, 4455, "생활관 후보자 추가모집 안내"),
            board,
        )

        self.assertEqual(len(posts), 1)
        self.assertEqual(posts[0]["number"], 4455)
        self.assertEqual(posts[0]["title"], "생활관 후보자 추가모집 안내")
        self.assertEqual(posts[0]["board_key"], board["key"])
        self.assertEqual(posts[0]["board_url"], board["url"])
        self.assertEqual(posts[0]["link"], f"{board['url']}/4455")

    def test_pinned_rows_marked_notice_are_still_parsed(self):
        board = BOARDS[0]
        posts = parse_notice_list(
            make_notice_list_html(board, 4455, "핀 고정 공지", display_number="공지"),
            board,
        )

        self.assertEqual(len(posts), 1)
        self.assertEqual(posts[0]["number"], 4455)

    def test_get_latest_notices_requests_the_board(self):
        class FakeResponse:
            def __init__(self, text):
                self.text = text

            def raise_for_status(self):
                return None

        board = BOARDS[0]
        with patch.object(crawler.requests, "Session") as session_class:
            session = session_class.return_value
            session.get.side_effect = [
                FakeResponse(make_notice_list_html(board, 1, board["name"]))
            ]

            posts_by_board = crawler.get_latest_notices()

        self.assertEqual(session.get.call_args_list[0].args[0], board["url"])
        self.assertEqual(set(posts_by_board), {board["key"]})

    def test_notice_details_uses_the_board_as_referer(self):
        class FakeResponse:
            text = '<div id="bo_v_con"><p>본문</p></div>'

            def raise_for_status(self):
                return None

        board = BOARDS[0]
        page_url = f"{board['url']}/4455"
        with patch.object(
            crawler.requests, "get", return_value=FakeResponse()
        ) as request:
            details = crawler.get_notice_details(page_url, board["url"])

        self.assertEqual(details["content"], "본문")
        self.assertEqual(
            request.call_args.kwargs["headers"]["Referer"],
            board["url"],
        )

    def test_refresh_download_url_uses_current_session_nonce(self):
        referer = "https://dorm.knu.ac.kr/app/board24/4455"
        file_info = {
            "name": "안내.pdf",
            "url": (
                "https://dorm.knu.ac.kr/app/bbs/download.php"
                "?bo_table=board24&wr_id=4455&no=0&nonce=old"
            ),
        }
        page_html = """
        <section id="bo_v_file">
          <a class="view_file_download"
             href="/app/bbs/download.php?bo_table=board24&amp;wr_id=4455&amp;no=0&amp;nonce=fresh">
            <strong>안내.pdf</strong>
          </a>
        </section>
        """

        refreshed_url = refresh_download_url(file_info, page_html, referer)

        self.assertEqual(
            refreshed_url,
            (
                "https://dorm.knu.ac.kr/app/bbs/download.php"
                "?bo_table=board24&wr_id=4455&no=0&nonce=fresh"
            ),
        )

    def test_refresh_download_url_leaves_inline_image_unchanged(self):
        image_url = "https://example.com/image.png"

        self.assertEqual(
            refresh_download_url(
                {"name": "image.png", "url": image_url},
                '<div id="bo_v_file"></div>',
                BOARDS[0]["url"],
            ),
            image_url,
        )

    def test_parse_notice_details(self):
        html = """
        <div id="bo_v_con">
          <p>첫 번째 <strong>중요 문단</strong>입니다.<br>다음 줄입니다.</p>
          <p><em>두 번째 문단</em>입니다.</p>
          <a href="/survey">설문 참여</a>
          <ul><li>첫 항목</li><li>둘째 항목</li></ul>
          <table><tr><th>구분</th><th>내용</th></tr><tr><td>A</td><td>B</td></tr></table>
          <img src="/images/notice.png" alt="안내 이미지.png">
        </div>
        <section id="bo_v_file">
          <a class="view_file_download" href="/bbs/download.php?no=0">
            <strong>신청서.hwp</strong>
          </a>
        </section>
        """

        details = parse_notice_details(html, "https://dorm.knu.ac.kr/app/board24/1")

        self.assertIn("첫 번째 중요 문단입니다.\n다음 줄입니다.", details["content"])
        self.assertIn("두 번째 문단입니다.", details["content"])
        self.assertIn(
            "설문 참여 (https://dorm.knu.ac.kr/survey)",
            details["content"],
        )
        markdown = "\n\n".join(details["content_markdown_blocks"])
        self.assertIn(r"*중요 문단*", markdown)
        self.assertIn(r"_두 번째 문단_", markdown)
        self.assertIn(
            r"[설문 참여](https://dorm.knu.ac.kr/survey)",
            markdown,
        )
        self.assertIn("• 첫 항목", markdown)
        self.assertIn("```\n구분 | 내용", markdown)
        self.assertEqual(details["attachments"][0]["name"], "신청서.hwp")
        self.assertEqual(
            details["inline_images"][0]["url"],
            "https://dorm.knu.ac.kr/images/notice.png",
        )

    def test_long_notice_is_split_without_losing_content(self):
        post = {
            "title": "실제 공지 제목",
            "content": "가" * (TELEGRAM_MESSAGE_LIMIT * 2),
            "link": "https://example.com/notice",
        }

        messages = build_notice_messages(post)

        self.assertGreater(len(messages), 1)
        self.assertTrue(all(len(message) <= TELEGRAM_MESSAGE_LIMIT for message in messages))
        combined = "".join(messages).replace("\n", "")
        self.assertIn("가" * (TELEGRAM_MESSAGE_LIMIT * 2), combined)
        self.assertTrue(messages[0].startswith("📢 *실제 공지 제목*"))

    def test_headline_messages_keep_board_title_and_link_only(self):
        post = {
            "title": "실제 공지 제목",
            "board_name": "생활관 공지사항",
            "content": "본문은 보내지 않습니다.",
            "content_markdown_blocks": ["본문은 보내지 않습니다\\."],
            "link": "https://example.com/notice",
        }

        messages = build_headline_messages(post)

        self.assertEqual(len(messages), 1)
        self.assertIn(r"\[생활관 공지사항\] 실제 공지 제목", messages[0])
        self.assertIn("https://example.com/notice", messages[0])
        self.assertNotIn("본문은 보내지 않습니다", messages[0])

    def test_markdown_special_characters_are_escaped(self):
        html = """
        <div id="bo_v_con">
          <p><strong>필수!</strong> 신청기간: 6.29~6.30</p>
          <p><span style="font-weight: 700">굵게</span></p>
          <p><span style="text-decoration: underline">연속</span><span style="text-decoration: underline">밑줄</span></p>
        </div>
        """

        blocks = html_content_to_markdown_blocks(
            BeautifulSoup(html, "html.parser").select_one("#bo_v_con")
        )

        self.assertEqual(
            blocks,
            [
                r"*필수\!* 신청기간: 6\.29\~6\.30",
                r"*굵게*",
                r"__연속밑줄__",
            ],
        )

    def test_table_cell_paragraphs_stay_in_one_row(self):
        html = """
        <div id="bo_v_con">
          <table>
            <tr>
              <td><p>구분</p></td>
              <td><p>졸업기준</p><p>학점</p></td>
              <td><p>총이수</p><p>학점</p></td>
            </tr>
            <tr><td>1</td><td>140</td><td>150</td></tr>
          </table>
        </div>
        """
        content = BeautifulSoup(html, "html.parser").select_one("#bo_v_con")

        blocks = html_content_to_markdown_blocks(content)
        table = next(block for block in blocks if block.startswith("```"))
        lines = table.splitlines()

        self.assertIn("구분 | 졸업기준 학점 | 총이수 학점", lines[1])
        self.assertIn("1    | 140", lines[3])
        header_cells = lines[1].split(" | ")
        data_cells = lines[3].split(" | ")
        self.assertEqual(
            [get_display_width(cell) for cell in header_cells[:-1]],
            [get_display_width(cell) for cell in data_cells[:-1]],
        )

    def test_table_rowspan_and_colspan_are_expanded(self):
        html = """
        <table>
          <tr><th rowspan="2">구분</th><th colspan="2">점수</th></tr>
          <tr><th>중간</th><th>기말</th></tr>
          <tr><td>A</td><td>90</td><td>95</td></tr>
        </table>
        """
        table = BeautifulSoup(html, "html.parser").select_one("table")

        self.assertEqual(
            extract_table_matrix(table),
            [
                ["구분", "점수", "점수"],
                ["구분", "중간", "기말"],
                ["A", "90", "95"],
            ],
        )

    def test_safe_filename(self):
        self.assertEqual(safe_filename('신청서:최종?.hwp'), "신청서_최종_.hwp")


if __name__ == "__main__":
    unittest.main()

import asyncio
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import bot
import config
from database import Database


class FakeMessage:
    def __init__(self):
        self.replies = []
        self.edits = []

    async def reply_text(self, text, reply_markup=None):
        self.replies.append(SimpleNamespace(text=text, reply_markup=reply_markup))


class FakeCallbackQuery:
    def __init__(self, data, message):
        self.data = data
        self.message = message
        self.answers = []
        self.edits = []

    async def answer(self, text=None, show_alert=False):
        self.answers.append(text)

    async def edit_message_text(self, text, reply_markup=None):
        self.edits.append(SimpleNamespace(text=text, reply_markup=reply_markup))


def make_update(chat_id, callback_data=None):
    message = FakeMessage()
    query = FakeCallbackQuery(callback_data, message) if callback_data else None
    return SimpleNamespace(
        effective_chat=SimpleNamespace(id=chat_id),
        effective_message=message,
        callback_query=query,
    )


class BotTestCase(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self._directory = tempfile.TemporaryDirectory()
        self.addCleanup(self._directory.cleanup)
        self.db_path = Path(self._directory.name) / "bot.db"
        self.database = Database(self.db_path)
        self.addCleanup(self.database.close)
        self.context = SimpleNamespace(
            application=SimpleNamespace(bot_data={"database": self.database}),
            bot=AsyncMock(),
        )


class CommandTest(BotTestCase):
    async def test_start_registers_a_new_user_with_everything_on(self):
        update = make_update(1001)

        await bot.start_command(update, self.context)

        settings = self.database.get_settings(1001)
        self.assertTrue(settings["active"])
        self.assertTrue(all(settings[key] for key in config.SUBSCRIPTION_KEYS))
        self.assertIn("공지 알림을 시작합니다", update.effective_message.replies[0].text)

    async def test_start_again_keeps_the_existing_settings(self):
        await bot.start_command(make_update(1001), self.context)
        self.database.toggle_option(1001, "include_content")

        update = make_update(1001)
        await bot.start_command(update, self.context)

        settings = self.database.get_settings(1001)
        self.assertFalse(settings["include_content"])
        self.assertIn("다시 시작합니다", update.effective_message.replies[0].text)

    async def test_start_reactivates_a_stopped_user(self):
        await bot.start_command(make_update(1001), self.context)
        self.database.toggle_option(1001, "include_attachments")
        await bot.stop_command(make_update(1001), self.context)
        self.assertFalse(self.database.get_settings(1001)["active"])

        await bot.start_command(make_update(1001), self.context)

        settings = self.database.get_settings(1001)
        self.assertTrue(settings["active"])
        self.assertFalse(settings["include_attachments"])

    async def test_stop_keeps_the_user_and_settings(self):
        await bot.start_command(make_update(1001), self.context)

        update = make_update(1001)
        await bot.stop_command(update, self.context)

        settings = self.database.get_settings(1001)
        self.assertFalse(settings["active"])
        self.assertTrue(settings["admission"])
        self.assertIn("중지", update.effective_message.replies[0].text)

    async def test_settings_shows_a_toggle_for_every_option(self):
        await bot.start_command(make_update(1001), self.context)

        update = make_update(1001)
        await bot.settings_command(update, self.context)

        reply = update.effective_message.replies[0]
        buttons = [
            button
            for row in reply.reply_markup.inline_keyboard
            for button in row
        ]
        self.assertEqual(
            [button.callback_data for button in buttons],
            [f"toggle:{key}" for key in config.SUBSCRIPTION_KEYS]
            + [f"toggle_meal:{key}" for key in config.DORM_KEYS]
            + ["enable:all", "disable:all"],
        )
        # 기숙사 3개는 한 줄에 나란히 배치되고, 전체 켜기/끄기는 맨 아래에 옵니다.
        rows = reply.reply_markup.inline_keyboard
        meal_row = rows[len(config.SUBSCRIPTION_KEYS)]
        self.assertEqual(
            [button.callback_data for button in meal_row],
            [f"toggle_meal:{key}" for key in config.DORM_KEYS],
        )
        self.assertEqual(
            [button.callback_data for button in rows[-1]],
            ["enable:all", "disable:all"],
        )
        self.assertIn("공지 알림 설정", reply.text)
        self.assertIn("🍚 식단표", reply.text)
        for dorm in config.DORMS:
            self.assertIn(dorm["name"], reply.text)

    async def test_help_lists_every_command(self):
        update = make_update(1001)

        await bot.help_command(update, self.context)

        text = update.effective_message.replies[0].text
        for command in ("/start", "/settings", "/stop", "/help"):
            self.assertIn(command, text)


class CallbackTest(BotTestCase):
    async def test_each_toggle_updates_the_same_message(self):
        await bot.start_command(make_update(1001), self.context)

        for key in config.SUBSCRIPTION_KEYS:
            with self.subTest(option=key):
                update = make_update(1001, callback_data=f"toggle:{key}")
                await bot.settings_callback(update, self.context)

                self.assertFalse(self.database.get_settings(1001)[key])
                # 새 메시지가 아니라 기존 메시지를 갱신해야 합니다.
                self.assertEqual(len(update.callback_query.edits), 1)
                self.assertEqual(update.effective_message.replies, [])
                self.assertEqual(len(update.callback_query.answers), 1)

    async def test_enable_and_disable_all_buttons(self):
        await bot.start_command(make_update(1001), self.context)

        await bot.settings_callback(
            make_update(1001, callback_data="disable:all"), self.context
        )
        settings = self.database.get_settings(1001)
        self.assertFalse(any(settings[key] for key in config.SUBSCRIPTION_KEYS))

        await bot.settings_callback(
            make_update(1001, callback_data="enable:all"), self.context
        )
        settings = self.database.get_settings(1001)
        self.assertTrue(all(settings[key] for key in config.SUBSCRIPTION_KEYS))

    async def test_callback_from_an_unknown_user_is_answered(self):
        update = make_update(9999, callback_data="toggle:admission")

        await bot.settings_callback(update, self.context)

        self.assertEqual(len(update.callback_query.answers), 1)
        self.assertEqual(update.callback_query.edits, [])

    async def test_meal_dorm_toggles_are_independent_of_notice_subscriptions(self):
        await bot.start_command(make_update(1001), self.context)

        update = make_update(1001, callback_data="toggle_meal:cheomseong")
        await bot.settings_callback(update, self.context)

        settings = self.database.get_settings(1001)
        self.assertTrue(settings["meal_cheomseong"])
        self.assertFalse(settings["meal_nuri"])
        self.assertTrue(settings["admission"])
        self.assertEqual(len(update.callback_query.edits), 1)

    async def test_unknown_callback_data_is_ignored(self):
        await bot.start_command(make_update(1001), self.context)
        update = make_update(1001, callback_data="toggle:active")

        await bot.settings_callback(update, self.context)

        self.assertEqual(update.callback_query.edits, [])
        self.assertEqual(len(update.callback_query.answers), 1)


class NoticeCheckTest(BotTestCase):
    def make_posts(self, numbers, board=None):
        board = board or config.BOARDS[0]
        return {
            board["key"]: [
                {
                    "number": number,
                    "title": f"{board['name']} {number}번 글",
                    "link": f"{board['url']}/{number}",
                    "board_key": board["key"],
                    "board_name": board["name"],
                    "board_url": board["url"],
                }
                for number in numbers
            ]
        }

    DETAILS = {
        "content": "본문",
        "content_markdown_blocks": ["본문"],
        "attachments": [],
        "inline_images": [],
    }

    async def run_check(self, posts_by_board, deliver_result=True):
        deliver = AsyncMock(return_value=deliver_result)
        with (
            patch.object(bot.crawler, "get_latest_notices", return_value=posts_by_board),
            patch.object(bot.crawler, "get_notice_details", return_value=self.DETAILS),
            patch.object(bot.Notifier, "deliver_notice", deliver),
            patch.object(bot.Notifier, "retry_pending_media", AsyncMock()),
        ):
            await bot.run_notice_check(self.context.bot, self.database)
        return deliver

    async def test_the_first_run_only_records_the_newest_notice(self):
        deliver = await self.run_check(self.make_posts([4454, 4455]))

        deliver.assert_not_awaited()
        self.assertEqual(self.database.get_last_numbers()["admission"], 4455)

    async def test_new_notices_go_only_to_active_subscribers(self):
        self.database.set_last_number("admission", 4455)
        self.database.ensure_user(1)
        self.database.ensure_user(2)
        self.database.set_active(2, False)

        deliver = await self.run_check(self.make_posts([4455, 4456]))

        deliver.assert_awaited_once()
        post, recipients = deliver.await_args.args
        self.assertEqual(post["number"], 4456)
        self.assertEqual([row["chat_id"] for row in recipients], [1])
        self.assertEqual(self.database.get_last_numbers()["admission"], 4456)

    async def test_a_restart_does_not_resend_the_same_notice(self):
        self.database.set_last_number("admission", 4455)
        self.database.ensure_user(1)
        posts = self.make_posts([4456])

        await self.run_check(posts)
        self.database.close()

        # 컨테이너 재시작을 흉내 내어 같은 DB 파일을 다시 엽니다.
        self.database = Database(self.db_path)
        self.addCleanup(self.database.close)
        deliver = await self.run_check(self.make_posts([4456]))

        deliver.assert_not_awaited()
        self.assertEqual(self.database.get_last_numbers()["admission"], 4456)

    async def test_a_failed_delivery_keeps_the_cursor_for_a_retry(self):
        self.database.set_last_number("admission", 4455)
        self.database.ensure_user(1)

        await self.run_check(self.make_posts([4456, 4457]), deliver_result=False)

        self.assertEqual(self.database.get_last_numbers()["admission"], 4455)

    async def test_the_cursor_advances_even_when_nobody_subscribes(self):
        self.database.set_last_number("admission", 4455)

        with patch.object(bot.crawler, "get_notice_details") as get_details:
            deliver = await self.run_check(self.make_posts([4456]))

        deliver.assert_not_awaited()
        get_details.assert_not_called()
        self.assertEqual(self.database.get_last_numbers()["admission"], 4456)

    async def test_a_detail_failure_stops_the_board_without_losing_the_notice(self):
        self.database.set_last_number("admission", 4455)
        self.database.ensure_user(1)
        deliver = AsyncMock(return_value=True)

        with (
            patch.object(
                bot.crawler,
                "get_latest_notices",
                return_value=self.make_posts([4456, 4457]),
            ),
            patch.object(
                bot.crawler, "get_notice_details", side_effect=RuntimeError("조회 실패")
            ),
            patch.object(bot.Notifier, "deliver_notice", deliver),
            patch.object(bot.Notifier, "retry_pending_media", AsyncMock()),
        ):
            await bot.run_notice_check(self.context.bot, self.database)

        deliver.assert_not_awaited()
        self.assertEqual(self.database.get_last_numbers()["admission"], 4455)

    async def test_each_board_keeps_its_own_cursor(self):
        posts = {}
        for board, number in zip(config.BOARDS, (4456, 4272)):
            self.database.set_last_number(board["key"], number - 1)
            posts.update(self.make_posts([number], board))
        self.database.ensure_user(1)

        deliver = await self.run_check(posts)

        self.assertEqual(deliver.await_count, 2)
        self.assertEqual(
            self.database.get_last_numbers(),
            {"admission": 4456, "btl": 4272},
        )


class MealCommandTest(BotTestCase):
    def make_meal(self, dorm_name, suffix=""):
        return {
            "dorm": dorm_name,
            "date": "2026-09-03",
            "breakfast": f"아침{suffix}",
            "lunch": f"점심{suffix}",
            "dinner": f"저녁{suffix}",
        }

    async def test_no_dorm_selected_shows_a_guidance_message(self):
        await bot.start_command(make_update(1001), self.context)

        update = make_update(1001)
        await bot.meal_command(update, self.context)

        text = update.effective_message.replies[0].text
        self.assertIn("선택된 기숙사가 없습니다", text)
        self.assertIn("/settings", text)

    async def test_single_dorm_output_includes_all_three_meals(self):
        await bot.start_command(make_update(1001), self.context)
        self.database.toggle_meal_dorm(1001, "cheomseong")

        update = make_update(1001)
        with patch.object(
            bot.meal_crawler, "get_today_meal", return_value=self.make_meal("첨성관")
        ):
            await bot.meal_command(update, self.context)

        text = update.effective_message.replies[0].text
        self.assertIn("🏠 첨성관", text)
        self.assertIn("🌅 아침\n아침", text)
        self.assertIn("☀️ 점심\n점심", text)
        self.assertIn("🌙 저녁\n저녁", text)
        self.assertNotIn("누리관", text)
        self.assertNotIn("보람관", text)

    async def test_multiple_dorms_are_all_reported_in_one_command(self):
        await bot.start_command(make_update(1001), self.context)
        self.database.toggle_meal_dorm(1001, "cheomseong")
        self.database.toggle_meal_dorm(1001, "boram")

        update = make_update(1001)
        with patch.object(
            bot.meal_crawler,
            "get_today_meal",
            side_effect=lambda dorm_key: self.make_meal(config.DORM_NAMES[dorm_key]),
        ):
            await bot.meal_command(update, self.context)

        text = update.effective_message.replies[0].text
        self.assertIn("🏠 첨성관", text)
        self.assertIn("🏠 보람관", text)
        self.assertLess(text.index("첨성관"), text.index("보람관"))

    async def test_a_failed_dorm_does_not_block_the_others(self):
        await bot.start_command(make_update(1001), self.context)
        self.database.toggle_meal_dorm(1001, "cheomseong")
        self.database.toggle_meal_dorm(1001, "nuri")

        def fake_get_today_meal(dorm_key):
            if dorm_key == "nuri":
                raise RuntimeError("페이지 구조 변경")
            return self.make_meal(config.DORM_NAMES[dorm_key])

        update = make_update(1001)
        with patch.object(
            bot.meal_crawler, "get_today_meal", side_effect=fake_get_today_meal
        ):
            await bot.meal_command(update, self.context)

        text = update.effective_message.replies[0].text
        self.assertIn("🏠 첨성관", text)
        self.assertIn("🌅 아침\n아침", text)
        self.assertIn("🏠 누리관\n식단을 불러오지 못했습니다.", text)

    async def test_bab_and_meal_produce_identical_output(self):
        await bot.start_command(make_update(1001), self.context)
        self.database.toggle_meal_dorm(1001, "cheomseong")

        with patch.object(
            bot.meal_crawler, "get_today_meal", return_value=self.make_meal("첨성관")
        ):
            # /bab 과 /meal 은 같은 핸들러 함수를 공유하므로 반복 호출로도
            # 결과가 동일함을 확인합니다 (아래 등록 테스트가 핸들러가 같음을 보장합니다).
            bab_update = make_update(1001)
            await bot.meal_command(bab_update, self.context)

            meal_update = make_update(1001)
            await bot.meal_command(meal_update, self.context)

        self.assertEqual(
            bab_update.effective_message.replies[0].text,
            meal_update.effective_message.replies[0].text,
        )

    async def test_bab_and_meal_are_registered_to_the_same_handler(self):
        with patch.object(bot.config, "TELEGRAM_TOKEN", "123456:test-token"):
            application = bot.build_application(self.database)
        handlers = application.handlers[0]

        commands_to_callbacks = {
            command: handler.callback
            for handler in handlers
            if isinstance(handler, bot.CommandHandler)
            for command in handler.commands
        }

        self.assertIs(commands_to_callbacks["bab"], bot.meal_command)
        self.assertIs(commands_to_callbacks["meal"], bot.meal_command)

    async def test_a_long_meal_message_is_split_within_the_telegram_limit(self):
        await bot.start_command(make_update(1001), self.context)
        self.database.toggle_meal_dorm(1001, "cheomseong")

        long_meal = self.make_meal("첨성관", suffix="가" * config.TELEGRAM_MESSAGE_LIMIT)
        update = make_update(1001)
        with patch.object(bot.meal_crawler, "get_today_meal", return_value=long_meal):
            await bot.meal_command(update, self.context)

        replies = update.effective_message.replies
        self.assertGreater(len(replies), 1)
        for reply in replies:
            self.assertLessEqual(len(reply.text), config.TELEGRAM_MESSAGE_LIMIT)


class CrawlJobTest(BotTestCase):
    async def test_a_second_run_is_skipped_while_one_is_already_in_progress(self):
        started = asyncio.Event()
        finish = asyncio.Event()

        async def slow_check(*_args, **_kwargs):
            started.set()
            await finish.wait()

        check_mock = AsyncMock(side_effect=slow_check)
        with patch.object(bot, "run_notice_check", check_mock):
            first_task = asyncio.create_task(bot.check_notices_job(self.context))
            await started.wait()
            # 첫 실행이 아직 락을 쥐고 있으므로 이번 호출은 바로 건너뜁니다.
            await bot.check_notices_job(self.context)
            finish.set()
            await first_task

        self.assertEqual(check_mock.await_count, 1)


if __name__ == "__main__":
    unittest.main()

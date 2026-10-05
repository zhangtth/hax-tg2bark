import copy
import os
import tempfile
import unittest
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

with patch.dict(os.environ, {
    "TG_API_ID": "1", "TG_API_HASH": "test", "TG_SESSION": "test", "BARK_KEY": "test"
}):
    import monitor


def message(mid, out=False):
    return SimpleNamespace(id=mid, text=f"notice {mid}", out=out)


class DeliveryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.state_patch = patch.object(monitor, "STATE_FILE", str(Path(self.tmp.name) / "state.json"))
        self.state_patch.start()
        self.addCleanup(self.state_patch.stop)
        self.target_patch = patch.object(monitor, "FORWARD_TO", "haxeu_musebot")
        self.target_patch.start()
        self.addCleanup(self.target_patch.stop)
        self.client = SimpleNamespace(
            get_entity=AsyncMock(return_value=SimpleNamespace(bot=True)),
            forward_messages=AsyncMock(return_value=SimpleNamespace(id=999)),
        )

        @asynccontextmanager
        async def connection():
            yield self.client

        self.connection_patch = patch.object(monitor, "telegram_client", connection)
        self.connection_patch.start()
        self.addCleanup(self.connection_patch.stop)

    async def run_main(self, state, msgs):
        monitor.save_state(copy.deepcopy(state))
        with patch.object(monitor, "fetch_messages", AsyncMock(return_value=msgs)) as fetch, patch.object(
            monitor, "safe_bark", return_value=True
        ) as bark:
            await monitor.main()
        return fetch, bark

    async def test_migration_skips_history_and_empty_checks_bot(self):
        fetch, bark = await self.run_main({"last_id": 10}, [])
        fetch.assert_awaited_once_with(10)
        self.client.get_entity.assert_awaited_once_with("haxeu_musebot")
        self.client.forward_messages.assert_not_awaited()
        self.assertEqual(monitor.load_state()["forward_last_id"], 10)
        bark.assert_not_called()

    async def test_new_messages_both_channels_in_order(self):
        _, bark = await self.run_main({"last_id": 10}, [message(12), message(11)])
        self.assertEqual([c.args[1] for c in self.client.forward_messages.await_args_list], [11, 12])
        self.assertEqual(bark.call_count, 2)
        self.assertEqual(monitor.load_state()["forward_last_id"], 12)
        self.assertEqual(monitor.load_state()["last_id"], 12)

    async def test_forward_retry_does_not_repeat_bark(self):
        fetch, bark = await self.run_main({"last_id": 12, "forward_last_id": 10}, [message(12), message(11)])
        fetch.assert_awaited_once_with(10)
        bark.assert_not_called()
        self.assertEqual(self.client.forward_messages.await_count, 2)

    async def test_forward_failure_preserves_partial_progress_and_bark(self):
        self.client.forward_messages.side_effect = [SimpleNamespace(id=999), RuntimeError("test")]
        with self.assertRaises(monitor.TelegramForwardError):
            await self.run_main({"last_id": 10}, [message(12), message(11)])
        state = monitor.load_state()
        self.assertEqual(state["last_id"], 12)
        self.assertEqual(state["forward_last_id"], 11)

    async def test_bark_failure_does_not_undo_forward_progress(self):
        monitor.save_state({"last_id": 10})
        with patch.object(monitor, "fetch_messages", AsyncMock(return_value=[message(11)])), patch.object(
            monitor, "safe_bark", return_value=False
        ), self.assertRaises(monitor.BarkNotificationError):
            await monitor.main()
        self.assertEqual(monitor.load_state()["last_id"], 10)
        self.assertEqual(monitor.load_state()["forward_last_id"], 11)

    async def test_outgoing_commands_not_forwarded(self):
        await self.run_main({"last_id": 10}, [message(11, out=True)])
        self.client.forward_messages.assert_not_awaited()
        self.assertEqual(monitor.load_state()["forward_last_id"], 11)

    async def test_non_bot_rejected_without_blocking_bark(self):
        self.client.get_entity.return_value = SimpleNamespace(bot=False)
        with self.assertRaises(monitor.TelegramForwardError):
            await self.run_main({"last_id": 10}, [message(11)])
        self.client.forward_messages.assert_not_awaited()
        self.assertEqual(monitor.load_state()["last_id"], 11)

    async def test_disabled_keeps_existing_behavior(self):
        with patch.object(monitor, "FORWARD_TO", ""):
            _, bark = await self.run_main({"last_id": 10}, [message(11)])
        self.client.get_entity.assert_not_awaited()
        self.assertEqual(bark.call_count, 1)

    async def test_manual_forward_only_latest_without_state_or_bark(self):
        async def history(*args, **kwargs):
            for m in [message(13, out=True), message(12), message(11)]:
                yield m

        self.client.iter_messages = history
        with patch.object(monitor, "save_state") as save, patch.object(monitor, "safe_bark") as bark:
            await monitor.test_forward_latest()
        self.client.forward_messages.assert_awaited_once()
        self.assertEqual(self.client.forward_messages.await_args.args[1], 12)
        save.assert_not_called()
        bark.assert_not_called()

    async def test_manual_empty_history_sends_nothing(self):
        async def history(*args, **kwargs):
            for m in []:
                yield m

        self.client.iter_messages = history
        with self.assertRaises(monitor.TelegramForwardError):
            await monitor.test_forward_latest()
        self.client.forward_messages.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()

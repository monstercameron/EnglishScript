import asyncio
import unittest
from types import SimpleNamespace

from englishscript.compiler import EnglishError, _EndProgram, compile_source


class AsyncRunTests(unittest.IsolatedAsyncioTestCase):
    async def test_pending_reply_keeps_world_and_does_not_repeat_output(self):
        outputs, worlds, requests = [], [], []
        future = asyncio.get_running_loop().create_future()

        async def model(question, state, shape, complaint):
            requests.append(question)
            return await future

        program = compile_source('Say "before".\nAsk the model "Q" and let the n (number) be the reply.\nSay the n.\n')
        task = asyncio.create_task(program.run_async(out=outputs.append, model=model, on_world=worlds.append))
        await asyncio.sleep(0)
        self.assertEqual(outputs, ['before'])
        self.assertEqual(requests, ['Q'])
        events = []
        self.assertTrue(worlds[0].event(lambda: events.append('input')))
        future.set_result('42')
        self.assertIs(await task, worlds[0])
        self.assertEqual(events, ['input'])
        self.assertEqual(outputs, ['before', '42'])

    async def test_nested_request_is_refused(self):
        program = compile_source('Try:\n  Ask the model "Q" and let the n (number) be the reply.\n'
                                 'If that fails:\n  Say "caught".\n')
        async def model(*args):
            return '1'
        with self.assertRaisesRegex(EnglishError, 'Only a top-level model question'):
            await program.run_async(model=model)

    async def test_model_worked_out_value_is_refused_before_calling_async_listener(self):
        calls = []
        async def model(*args):
            calls.append(args)
            return '3'
        source = ('To work out the count (number), ask the model "How many?".\n'
                  'Say the count.\n')
        with self.assertRaisesRegex(EnglishError, 'Only a top-level model question'):
            await compile_source(source).run_async(model=model)
        self.assertEqual(calls, [])
        output = []
        compile_source(source).run(out=output.append, model=lambda *args: '3')
        self.assertEqual(output, ['3'])

    async def test_bad_reply_is_retried_and_cached(self):
        calls, output = [], []
        async def model(question, state, shape, complaint):
            calls.append(complaint)
            return 'bad' if len(calls) == 1 else '3'
        program = compile_source('Ask the model "Q" and let the n (number) be the reply.\n'
                                 'Ask the model "Q" and let the m (number) be the reply.\nSay the n + the m.\n')
        await program.run_async(out=output.append, model=model)
        self.assertEqual(output, ['6'])
        self.assertEqual(len(calls), 2)
        self.assertIsNotNone(calls[1])

    async def test_late_reply_after_end_is_discarded_and_finishes(self):
        worlds, output, hooks = [], [], []
        future = asyncio.get_running_loop().create_future()
        async def model(*args):
            return await future
        program = compile_source('Ask the model "Q" and let the n (number) be the reply.\nSay the n.\n')
        program.compiler.libraries["test"] = (SimpleNamespace(
            live=lambda world: hooks.append("live"), finish=lambda world: hooks.append("finish")), None)
        task = asyncio.create_task(program.run_async(out=output.append, model=model, on_world=worlds.append))
        await asyncio.sleep(0)
        def end():
            raise _EndProgram()
        worlds[0].event(end)
        future.set_result('5')
        self.assertIs(await task, worlds[0])
        self.assertTrue(worlds[0].ended)
        self.assertFalse(worlds[0].busy)
        self.assertEqual(worlds[0].answers, {})
        self.assertEqual(output, [])
        self.assertEqual(hooks, ["finish"])

    async def test_cancelled_wait_finishes_and_rejects_events(self):
        worlds, hooks = [], []
        entered = asyncio.Event()
        async def model(*args):
            entered.set()
            await asyncio.Future()
        program = compile_source('Ask the model "Q" and let the n (number) be the reply.\n')
        program.compiler.libraries["test"] = (SimpleNamespace(
            live=lambda world: hooks.append("live"), finish=lambda world: hooks.append("finish")), None)
        task = asyncio.create_task(program.run_async(model=model, on_world=worlds.append))
        await entered.wait()
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertTrue(worlds[0].ended)
        self.assertFalse(worlds[0].busy)
        self.assertFalse(worlds[0].event(lambda: self.fail("ended world accepted an event")))
        self.assertEqual(hooks, ["finish"])

    async def test_listener_failure_finishes_and_keeps_source_location(self):
        worlds, hooks = [], []
        async def model(*args):
            raise ValueError("broken listener")
        program = compile_source('Ask the model "Q" and let the n (number) be the reply.\n')
        program.compiler.libraries["test"] = (SimpleNamespace(
            live=lambda world: hooks.append("live"), finish=lambda world: hooks.append("finish")), None)
        with self.assertRaisesRegex(EnglishError, 'broken listener') as caught:
            await program.run_async(model=model, on_world=worlds.append)
        self.assertIsNotNone(caught.exception.line)
        self.assertTrue(worlds[0].ended)
        self.assertFalse(worlds[0].busy)
        self.assertEqual(hooks, ["finish"])


if __name__ == '__main__':
    unittest.main()

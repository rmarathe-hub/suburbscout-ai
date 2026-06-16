"""Hosted agent run() contract tests."""

from __future__ import annotations

import asyncio
import unittest

from agent_framework import Content, Message

from app.hosted_query_agent import QueryPipelineHostedAgent


class TestHostedQueryAgentRunContract(unittest.TestCase):
    def test_stream_true_returns_async_iterator_not_coroutine(self) -> None:
        agent = QueryPipelineHostedAgent()
        result = agent.run(
            stream=True,
            messages=[Message(role="user", contents=[Content.from_text("hello")])],
        )
        self.assertFalse(asyncio.iscoroutine(result))
        self.assertTrue(hasattr(result, "__aiter__"))

    def test_stream_false_returns_awaitable(self) -> None:
        agent = QueryPipelineHostedAgent()
        result = agent.run(
            stream=False,
            messages=[Message(role="user", contents=[Content.from_text("hello")])],
        )
        self.assertTrue(asyncio.iscoroutine(result))


if __name__ == "__main__":
    unittest.main()

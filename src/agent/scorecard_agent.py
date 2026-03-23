"""LangGraph ReAct agent with LangSmith tracing for scorecard Q&A."""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from langchain_core.messages import AIMessage, HumanMessage
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent
from langsmith import traceable

from .database import DEFAULT_DB_PATH, init_db
from .tools import build_scorecard_tools

logger = logging.getLogger(__name__)

_DEFAULT_SYSTEM = """You are an analyst assistant for the Vision One Million regional scorecard.
Answer using the provided tools to read the local SQLite metrics database when numbers or comparisons are needed.
Explain briefly; cite values returned by tools. If data is missing, say so clearly."""


class ScorecardAgent:
    """
    Natural-language interface over scorecard metrics with tool calling and LangSmith traces.

    Environment (typically in ``.env``):
    - ``OPENAI_API_KEY`` — required for ``ChatOpenAI``.
    - ``LANGCHAIN_TRACING_V2=true`` — enable LangSmith tracing.
    - ``LANGCHAIN_API_KEY`` — LangSmith API key (often named like ``lsv2_pt_...``).
    - ``LANGCHAIN_PROJECT`` — project name in LangSmith (optional).
    """

    def __init__(
        self,
        db_path: str | Path | None = None,
        *,
        system_prompt: str | None = None,
    ) -> None:
        try:
            load_dotenv()
        except Exception as e:
            logger.warning("load_dotenv failed (continuing): %s", e)

        self._db_path = Path(db_path) if db_path else DEFAULT_DB_PATH
        try:
            init_db(self._db_path)
        except Exception as e:
            logger.exception("init_db failed: %s", e)
            raise

        try:
            self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        except Exception as e:
            logger.exception("SQLite connect failed: %s", e)
            raise

        try:
            self._llm = ChatOpenAI(
                model="gpt-4o-mini",
                temperature=0,
            )
        except Exception as e:
            logger.exception("ChatOpenAI init failed: %s", e)
            try:
                self._conn.close()
            except Exception:
                pass
            raise

        self._tools = build_scorecard_tools(self._db_path)
        try:
            self._agent = create_react_agent(
                self._llm,
                self._tools,
                prompt=system_prompt or _DEFAULT_SYSTEM,
            )
        except Exception as e:
            logger.exception("create_react_agent failed: %s", e)
            try:
                self._conn.close()
            except Exception:
                pass
            raise

    def close(self) -> None:
        try:
            self._conn.close()
        except Exception as e:
            logger.warning("connection close: %s", e)

    @traceable(name="ScorecardAgent.run")
    def run(self, query: str) -> str:
        """
        Run the ReAct agent on a natural language question; return the assistant's final reply text.
        """
        if not (query or "").strip():
            return "Please provide a non-empty question."

        try:
            result: dict[str, Any] = self._agent.invoke(
                {"messages": [HumanMessage(content=query.strip())]}
            )
        except Exception as e:
            logger.exception("agent invoke failed: %s", e)
            return f"Sorry, the agent could not complete this request: {e}"

        try:
            messages = result.get("messages") or []
            if not messages:
                return ""
            last = messages[-1]
            if isinstance(last, AIMessage):
                content = last.content
                if isinstance(content, str):
                    return content
                if isinstance(content, list):
                    parts: list[str] = []
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "text":
                            parts.append(str(block.get("text", "")))
                        else:
                            parts.append(str(block))
                    return "".join(parts)
            return str(getattr(last, "content", last))
        except Exception as e:
            logger.exception("parsing agent messages failed: %s", e)
            return f"Agent finished but the response could not be read: {e}"

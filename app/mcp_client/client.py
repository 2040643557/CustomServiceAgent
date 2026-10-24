"""MCP Client：同步封装，通过 Streamable HTTP 连接 MCP Server。

内部使用后台线程运行异步事件循环，对外暴露同步接口，
使得现有的同步 Agent 代码无需改动即可调用 MCP 工具。
"""

import asyncio
import json
import logging
import threading
from urllib.parse import urlparse

import httpx

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from app.mcp_client.converter import mcp_tools_to_openai

logger = logging.getLogger(__name__)

_LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}


def _root_exception(exc: BaseException) -> BaseException:
    """取出 ExceptionGroup 里最内层的异常，便于输出可读的错误信息。"""
    while isinstance(exc, BaseExceptionGroup) and exc.exceptions:
        exc = exc.exceptions[0]
    return exc


class MCPClient:
    """同步 MCP 客户端，通过 Streamable HTTP 连接远程 MCP Server。"""

    def __init__(
        self,
        server_url: str,
        connect_timeout: float = 30.0,
        call_timeout: float = 30.0,
    ):
        self._server_url = server_url
        self._connect_timeout = connect_timeout
        self._call_timeout = call_timeout
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._session: ClientSession | None = None
        self._connected = threading.Event()
        self._close_event: asyncio.Event | None = None

        host = (urlparse(server_url).hostname or "").lower()
        self._is_local = host in _LOCAL_HOSTS

    def connect(self) -> list[dict]:
        """连接 MCP Server，发现工具，返回 OpenAI 格式的工具定义列表。"""
        if self._thread and self._thread.is_alive():
            raise RuntimeError("MCP 客户端已连接，请先调用 close()")

        self._loop = asyncio.new_event_loop()
        self._close_event = asyncio.Event()
        self._connected = threading.Event()
        tool_definitions: list[dict] = []
        error_holder: list[Exception] = []

        def run_loop():
            self._loop.run_until_complete(self._run(tool_definitions, error_holder))

        self._thread = threading.Thread(target=run_loop, daemon=True)
        self._thread.start()

        connected = self._connected.wait(timeout=self._connect_timeout)

        if error_holder:
            root = _root_exception(error_holder[0])
            raise root from None

        if not connected:
            raise TimeoutError(
                f"MCP 连接超时（{self._connect_timeout:.0f} 秒）：{self._server_url}"
            )

        return tool_definitions

    async def _run(self, tool_definitions: list[dict], error_holder: list[Exception]):
        """后台协程：建立连接 → 发现工具 → 保持存活等待调用。"""
        # 本机地址不走系统代理：Windows 上 httpx 默认会读取注册表代理，
        # 若 127.0.0.1 不在 bypass 列表，初始化请求会被代理返回 502。
        # 远程地址保留 trust_env=True，以便企业代理环境下正常访问。
        timeout = httpx.Timeout(30.0, read=300.0)

        try:
            async with httpx.AsyncClient(
                trust_env=not self._is_local,
                timeout=timeout,
            ) as http_client:
                async with streamable_http_client(
                    self._server_url,
                    http_client=http_client,
                ) as (read, write, _):
                    async with ClientSession(read, write) as session:
                        await session.initialize()
                        self._session = session

                        tools_result = await session.list_tools()
                        openai_tools = mcp_tools_to_openai(tools_result.tools)
                        tool_definitions.extend(openai_tools)

                        self._connected.set()
                        await self._close_event.wait()
        except Exception as e:
            # 只在调试级别打印完整堆栈；正常降级由 ToolManager 输出简洁警告。
            logger.debug("MCP 连接失败: %s", e, exc_info=True)
            error_holder.append(e)
            self._connected.set()

    def call_tool(self, name: str, arguments: dict) -> str:
        """调用 MCP 工具，返回 JSON 字符串结果。"""
        if not self._session or not self._loop:
            return json.dumps({"error": "MCP 客户端未连接"}, ensure_ascii=False)

        future = asyncio.run_coroutine_threadsafe(
            self._session.call_tool(name, arguments), self._loop
        )
        try:
            result = future.result(timeout=self._call_timeout)
        except Exception as e:
            return json.dumps(
                {"error": f"MCP 工具调用出错: {e}"}, ensure_ascii=False
            )

        if result.isError:
            text = result.content[0].text if result.content else "未知错误"
            return json.dumps({"error": f"工具执行出错: {text}"}, ensure_ascii=False)

        return result.content[0].text if result.content else "{}"

    def close(self):
        """关闭 MCP 连接，清理后台线程与事件循环。"""
        if (
            self._close_event
            and self._loop
            and not self._loop.is_closed()
            and self._loop.is_running()
        ):
            self._loop.call_soon_threadsafe(self._close_event.set)

        if self._thread and self._thread is not threading.current_thread():
            self._thread.join(timeout=5)

        if (
            self._loop
            and not self._loop.is_closed()
            and (not self._thread or not self._thread.is_alive())
        ):
            self._loop.close()

        self._session = None
        self._close_event = None
        self._loop = None
        self._thread = None

import asyncio
import json
import logging
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Optional

import websockets
from websockets.asyncio.client import connect as ws_connect

from dglabv3.devices.base import FRAME_INTERVAL_MS, App, Device, OutputDevice
from dglabv3.devices.registry import DeviceRegistry
from dglabv3.dtype import Channel, Strength

if TYPE_CHECKING:
    from dglabv3.dglab import dglabv3

logger = logging.getLogger("dglabv3.protocol")


class Protocol(ABC):
    """
    通訊協議基底類別

    負責 WebSocket 連線、App 與設備狀態的維護，並實作設備操作
    由 dglabv3 透過 bind() 注入事件接收者與設備註冊表
    """

    default_url: str = ""

    def __init__(self, url: Optional[str] = None) -> None:
        self.url = url or self.default_url
        self.ws = None
        self.target_id: Optional[str] = None  # 控制方 ID，App 使用它配對
        self.apps: dict[str, App] = {}
        self.registry = DeviceRegistry.default()
        self._client: Optional["dglabv3"] = None
        self._bind_event = asyncio.Event()
        self._listen_task: Optional[asyncio.Task] = None
        self._tasks: list[asyncio.Task] = []

    def bind(self, client: "dglabv3", registry: DeviceRegistry) -> None:
        self._client = client
        self.registry = registry

    def is_connected(self) -> bool:
        return self.ws is not None and self.target_id is not None

    async def connect(self, timeout: float = 30) -> str:
        """
        連接伺服器並等待分配控制方 ID

        :return: 控制方 ID
        :raises ConnectionError: 連接失敗
        :raises TimeoutError: 等待超時
        """
        try:
            self.ws = await ws_connect(self.url)
        except Exception as e:
            logger.error(f"WebSocket connection error: {e}")
            raise ConnectionError("WebSocket connection error") from e
        logger.debug("WebSocket connected")
        self._listen_task = asyncio.create_task(self._listen())
        try:
            await asyncio.wait_for(self._bind_event.wait(), timeout)
        except asyncio.TimeoutError:
            logger.error("Bind timeout")
            await self.close()
            raise TimeoutError("Bind timeout")
        assert self.target_id is not None
        return self.target_id

    async def close(self) -> None:
        """
        關閉連線並清理資源
        """
        current = asyncio.current_task()
        for task in [self._listen_task, *self._tasks]:
            if task and not task.done() and task is not current:
                task.cancel()
        self._listen_task = None
        self._tasks.clear()
        if self.ws:
            try:
                await self.ws.close()
                logger.debug("WebSocket closed")
            except Exception as e:
                logger.error(f"Error on closing WebSocket: {e}")
        self.ws = None
        self._reset()

    def _reset(self) -> None:
        self.target_id = None
        self.apps.clear()
        self._bind_event.clear()

    def _start_task(self, coro) -> asyncio.Task:
        task = asyncio.create_task(coro)
        self._tasks.append(task)
        return task

    async def _listen(self) -> None:
        try:
            if self.ws is None:
                return
            async for message in self.ws:
                await self.handle_message(message)
        except websockets.ConnectionClosed as e:
            logger.info(f"WebSocket connection closed: {e}")
        except Exception as e:
            logger.error(f"WebSocket error: {e}")
        for task in self._tasks:
            task.cancel()
        self._tasks.clear()
        self.ws = None
        self._reset()
        await self._dispatch("disconnect")

    async def handle_message(self, data: websockets.Data) -> None:
        """
        處理收到的 WebSocket 訊息
        """
        try:
            frame = json.loads(data)
        except (TypeError, ValueError):
            logger.warning(f"Invalid message: {data!r}")
            return
        if not isinstance(frame, dict):
            return
        logger.debug(f"Received message: {frame}")
        try:
            await self._handle_frame(frame)
        except Exception as e:
            logger.warning(f"Error: {e}")
            logger.debug(f"Received raw message: {data}")

    async def _send_frame(self, frame: dict) -> None:
        if self.ws is None:
            raise ConnectionError("WebSocket not connected")
        text = json.dumps(frame, ensure_ascii=False, separators=(",", ":"))
        await self.ws.send(text)
        logger.debug(f"Sent message: {text}")

    async def _dispatch(self, name: str, *args: Any) -> None:
        if self._client is not None:
            await self._client._dispatch(name, *args)

    def _add_app(self, client_id: str) -> App:
        app = self.apps.get(client_id)
        if app is None:
            app = App(client_id, self, self.registry)
            self.apps[client_id] = app
        return app

    @staticmethod
    def _strength_snapshots(app: App) -> dict[str, Strength]:
        snapshots = {}
        for device in app:
            if isinstance(device, OutputDevice):
                strength = device.strength_snapshot()
                if strength is not None:
                    snapshots[device.slot_id] = strength
        return snapshots

    async def _dispatch_strength_changes(self, app: App, before: dict[str, Strength]) -> None:
        for slot_id, strength in self._strength_snapshots(app).items():
            if before.get(slot_id) != strength:
                await self._dispatch("strength", strength)

    @abstractmethod
    def qrcode_url(self) -> Optional[str]:
        """App 掃描用的 QR code 內容"""

    @abstractmethod
    async def _handle_frame(self, frame: dict) -> None:
        """處理已解析的訊息"""

    @abstractmethod
    async def add_strength(self, device: Device, channel: Channel, value: int, **options: Any) -> Any: ...

    @abstractmethod
    async def reset_strength(self, device: Device, channel: Channel, **options: Any) -> Any: ...

    @abstractmethod
    async def set_strength(self, device: Device, channel: Channel, value: int) -> Any: ...

    @abstractmethod
    async def set_temp_strength(
        self, device: Device, channel: Channel, value: int, duration: int, **options: Any
    ) -> Any: ...

    @abstractmethod
    async def send_pulse(
        self, device: Device, channel: Channel, frames: list[str], duration: int, **options: Any
    ) -> Any: ...

    async def send_wave(self, device: Device, channel: Channel, frames: list[str], time: int, **options: Any) -> Any:
        """
        發送波形並重複播放 time 秒，預設展開幀後呼叫 send_pulse
        """
        total = max(1, time * 1000 // FRAME_INTERVAL_MS)
        expanded = (frames * (total // len(frames) + 1))[:total]
        return await self.send_pulse(device, channel, expanded, time * 1000, **options)

    @abstractmethod
    async def clear(self, device: Device, channel: Channel) -> None: ...

    @abstractmethod
    async def clear_all(self, app: App) -> None: ...

import asyncio
import logging
import uuid
from enum import IntEnum
from typing import Any, Optional
from urllib.parse import quote

from dglabv3.devices.base import FRAME_INTERVAL_MS, App, Device, OutputDevice
from dglabv3.dtype import Channel, Priority
from dglabv3.errors import AppResponseError, DGLabError
from dglabv3.protocols.base import Protocol

logger = logging.getLogger("dglabv3.protocol.v4")

QRCODE_PREFIX = "https://dungeon-lab.cn/s/?v=1&action=socket&url="

_DEFAULT = -1.0


class ActionType(IntEnum):
    APPEND_PULSE_DATA = 0  # 推送波形 (持續任務)
    ADD_INTENSITY = 3  # 相對調整強度
    SET_TEMP_INTENSITY = 4  # 臨時強度，結束後歸零 (持續任務)
    SET_INTENSITY = 7  # 強度歸零 (協議只接受 0)


class V4Protocol(Protocol):
    """
    DG-LAB WebSocket V4 協議 (DG-LAB 4 App)

    支援多個 App 同時連接，每個 App 可暴露多個設備 (郊狼、負鼠、靈貓)
    設備操作會等待 App 回應，App 回傳錯誤時拋出 AppResponseError
    """

    default_url = "wss://trex.dungeon-lab.cn/v4"

    def __init__(self, url: Optional[str] = None, response_timeout: float = 8.0) -> None:
        """
        :param url: V4 伺服器地址
        :param response_timeout: 等待 App 回應的預設超時時間(秒)
        """
        super().__init__(url)
        self.url = self.url.rstrip("/")
        self.response_timeout = response_timeout
        self.ping_interval = 5
        self.max_missed_pongs = 3
        self._missed_pongs = 0
        self._pending: dict[tuple[str, str], tuple[asyncio.Future, Optional[asyncio.TimerHandle]]] = {}

    def qrcode_url(self) -> Optional[str]:
        app_url = self.app_url()
        return None if app_url is None else QRCODE_PREFIX + quote(app_url, safe="")

    def app_url(self) -> Optional[str]:
        """App 連接用的 WebSocket 地址"""
        if self.target_id is None:
            return None
        return f"{self.url}?tid={self.target_id}"

    def _reset(self) -> None:
        super()._reset()
        self._reject_pending(DGLabError("WebSocket disconnected"))

    async def _handle_frame(self, frame: dict) -> None:
        match frame.get("type"):
            case "hello":
                self.target_id = frame.get("clientId")
                self._missed_pongs = 0
                self._start_task(self._ping_loop())
                self._bind_event.set()
            case "client_attached":
                client_id = frame["clientId"]
                self._add_app(client_id)
                await self._dispatch("app_connect", client_id)
            case "client_disconnected":
                client_id = frame["clientId"]
                self.apps.pop(client_id, None)
                self._reject_pending(DGLabError("App disconnected"), client_id)
                await self._dispatch("app_disconnect", client_id)
            case "message":
                await self._on_app_message(frame.get("clientId"), frame.get("data"))
            case "pong":
                self._missed_pongs = 0
            case "heartbeat":
                pass
            case "idle_timeout":
                logger.warning("Idle timeout: no app connected within 5 minutes")
            case "error":
                logger.error(f"Server error: {frame.get('message') or frame.get('code')}")
            case other:
                logger.warning(f"Unknown message type: {other}")

    async def _on_app_message(self, client_id: Any, data: Any) -> None:
        if not isinstance(client_id, str) or not isinstance(data, dict):
            return
        if data.get("t") == "resp":
            self._resolve_response(client_id, data)
            return
        if data.get("t") != "ev":
            return

        app = self._add_app(client_id)
        before = self._strength_snapshots(app)
        match data.get("ev"):
            case "devices.snapshot":
                app.replace_devices(data.get("devices") or [])
                await self._dispatch("devices", list(app), client_id)
            case "devices.patch":
                app.patch_devices(data.get("added") or [], data.get("removed") or [])
                await self._dispatch("devices", list(app), client_id)
            case "slots.patch":
                for device in app.patch_slots(data.get("slots") or []):
                    await self._dispatch("device", device, client_id)
            case "custom.action":
                action = data.get("action")
                if isinstance(action, int) and 0 <= action <= 9:
                    await self._dispatch("action", action, client_id)
                return
            case other:
                logger.warning(f"Unknown app event: {other}")
                return
        await self._dispatch_strength_changes(app, before)

    async def _ping_loop(self) -> None:
        """
        伺服器級心跳，連續多次未收到 pong 則斷開
        """
        try:
            while True:
                await asyncio.sleep(self.ping_interval)
                if self._missed_pongs >= self.max_missed_pongs:
                    logger.error("Server ping timeout")
                    if self.ws:
                        await self.ws.close()
                    return
                self._missed_pongs += 1
                await self._send_frame({"type": "ping"})
        except asyncio.CancelledError:
            pass

    async def request(
        self,
        app: App,
        method: str,
        data: Optional[dict] = None,
        timeout: Optional[float] = _DEFAULT,
    ) -> asyncio.Future:
        """
        向 App 發送 RPC 請求

        :param method: RPC 方法名，例如 devices.get
        :param timeout: 等待回應的超時時間(秒)，None 為不限時
        :return: 回應結果的 Future
        """
        req_id = uuid.uuid4().hex[:16]
        request: dict[str, Any] = {"t": "req", "reqId": req_id, "m": method}
        if data is not None:
            request["data"] = data

        loop = asyncio.get_running_loop()
        future: asyncio.Future = loop.create_future()
        future.add_done_callback(_consume_exception)
        future.v4_method = method  # type: ignore[attr-defined]
        key = (app.client_id, req_id)
        if timeout == _DEFAULT:
            timeout = self.response_timeout
        timer = None if timeout is None else loop.call_later(timeout, self._settle, key, None, TimeoutError())
        self._pending[key] = (future, timer)

        try:
            await self._send_frame({"type": "message", "clientId": app.client_id, "data": request})
        except Exception as e:
            self._settle(key, exception=DGLabError(f"Send failed: {e}"))
        return future

    def _resolve_response(self, client_id: str, response: dict) -> None:
        key = (client_id, response.get("reqId") or response.get("requestId"))
        entry = self._pending.get(key)  # type: ignore[arg-type]
        if entry is None:
            return
        if response.get("error"):
            method = getattr(entry[0], "v4_method", None)
            self._settle(key, exception=AppResponseError(str(response["error"]), method))  # type: ignore[arg-type]
        else:
            self._settle(key, result=response.get("result"))  # type: ignore[arg-type]

    def _settle(self, key: tuple[str, str], result: Any = None, exception: Optional[BaseException] = None) -> None:
        entry = self._pending.pop(key, None)
        if entry is None:
            return
        future, timer = entry
        if timer is not None:
            timer.cancel()
        if future.done():
            return
        if exception is not None:
            future.set_exception(exception)
        else:
            future.set_result(result)

    def _reject_pending(self, error: Exception, client_id: Optional[str] = None) -> None:
        for key in list(self._pending):
            if client_id is None or key[0] == client_id:
                self._settle(key, exception=error)

    async def request_devices(self, app: App) -> list[Device]:
        """
        向 App 請求設備列表並更新快取 (通常不需要呼叫)
        """
        result = await (await self.request(app, "devices.get"))
        app.replace_devices(result.get("devices") or [])
        await self._dispatch("devices", list(app), app.client_id)
        return list(app)

    async def ping_app(self, app: App) -> int:
        """
        探測到 App 的鏈路

        :return: App 收到請求時的本地時間戳(毫秒)
        """
        return await (await self.request(app, "ping"))

    async def _operate(
        self,
        device: Device,
        channel: Channel,
        action: ActionType,
        fields: dict,
        wait: bool,
        priority: Optional[Priority],
        immediate: Optional[bool],
        timeout: Optional[float],
    ) -> Any:
        """
        發送 device.op

        :return: wait=True 時返回結果，否則返回 Future
        """
        op: dict[str, Any] = {"s": device.slot_id, "t": int(action), "c": int(channel) - 1}
        if priority is not None:
            op["p"] = int(priority)
        if immediate is not None:
            op["im"] = immediate
        op.update(fields)
        future = await self.request(device.app, "device.op", op, timeout)
        return await future if wait else future

    async def add_strength(
        self,
        device: Device,
        channel: Channel,
        value: int,
        wait: bool = True,
        priority: Optional[Priority] = None,
        immediate: Optional[bool] = None,
    ) -> Any:
        return await self._operate(
            device, channel, ActionType.ADD_INTENSITY, {"v": value}, wait, priority, immediate, _DEFAULT
        )

    async def reset_strength(
        self,
        device: Device,
        channel: Channel,
        wait: bool = True,
        priority: Optional[Priority] = None,
        immediate: Optional[bool] = None,
    ) -> Any:
        return await self._operate(
            device, channel, ActionType.SET_INTENSITY, {"v": 0}, wait, priority, immediate, _DEFAULT
        )

    async def set_strength(self, device: Device, channel: Channel, value: int) -> None:
        # V4 只能歸零或相對調整，根據 App 上報的當前強度計算差值
        current = device.get_strength(channel) if isinstance(device, OutputDevice) else None
        if current is None:
            await self.reset_strength(device, channel)
            current = 0
        if value != current:
            await self.add_strength(device, channel, value - current)

    async def set_temp_strength(
        self,
        device: Device,
        channel: Channel,
        value: int,
        duration: int,
        wait: bool = False,
        priority: Optional[Priority] = None,
        immediate: Optional[bool] = None,
    ) -> Any:
        timeout = None if duration <= 0 else max(self.response_timeout, duration / 1000 + 2)
        return await self._operate(
            device,
            channel,
            ActionType.SET_TEMP_INTENSITY,
            {"v": value, "d": duration},
            wait,
            priority,
            immediate,
            timeout,
        )

    async def send_pulse(
        self,
        device: Device,
        channel: Channel,
        frames: list[str],
        duration: int,
        wait: bool = False,
        priority: Optional[Priority] = None,
        immediate: Optional[bool] = None,
        version: Optional[int] = None,
    ) -> Any:
        fields: dict[str, Any] = {"d": duration, "v": frames}
        if version is not None:
            fields["ver"] = version
        play_ms = len(frames) * FRAME_INTERVAL_MS
        if duration > 0:
            play_ms = min(play_ms, duration)
        timeout = max(self.response_timeout, play_ms / 1000 + 2)
        return await self._operate(
            device, channel, ActionType.APPEND_PULSE_DATA, fields, wait, priority, immediate, timeout
        )

    async def clear(self, device: Device, channel: Channel) -> None:
        if channel == Channel.BOTH:
            await (await self.request(device.app, "device.op.clear", {"s": device.slot_id}))
        else:
            await (await self.request(device.app, "device.op.clear", {"s": device.slot_id, "c": int(channel) - 1}))

    async def clear_all(self, app: App) -> None:
        await (await self.request(app, "device.op.clear"))


def _consume_exception(future: asyncio.Future) -> None:
    if not future.cancelled() and future.exception() is not None:
        logger.debug(f"V4 request failed: {future.exception()}")

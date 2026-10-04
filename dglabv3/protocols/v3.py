import asyncio
import json
import logging
import math
from typing import Any, Optional

from dglabv3.devices.base import App, Device, OutputDevice, split_channel
from dglabv3.dtype import Channel, DeviceType, MessageType, StrengthMode, StrengthType
from dglabv3.errors import NotSupportedError
from dglabv3.protocols.base import Protocol
from dglabv3.wsmessage import WSMessage, WStype

logger = logging.getLogger("dglabv3.protocol.v3")

QRCODE_PREFIX = "https://www.dungeon-lab.com/app-download.php#DGLAB-SOCKET#"


class V3Protocol(Protocol):
    """
    DG-LAB WebSocket V3
    """

    default_url = "wss://ws.dungeon-lab.cn/"
    SLOT_ID = "v3"

    def __init__(self, url: Optional[str] = None) -> None:
        super().__init__(url)
        if not self.url.endswith("/"):
            self.url += "/"
        self.interval = 20
        self.disconnect_time = 30
        self.app_id: Optional[str] = None
        self._disconnect_count = 0

    def qrcode_url(self) -> Optional[str]:
        if self.target_id is None:
            return None
        return f"{QRCODE_PREFIX}{self.url}{self.target_id}"

    def _reset(self) -> None:
        super()._reset()
        self.app_id = None

    async def _handle_frame(self, frame: dict) -> None:
        message = WSMessage(frame)
        if message.type == WStype.BIND:
            if self.target_id is None and message.clientID:
                self.target_id = message.clientID
                self._start_task(self._heartbeat())
                self._bind_event.set()
            if message.targetID:
                await self._on_app_paired(message.targetID)

        elif message.type == WStype.BREAK:
            app_id = self.app_id
            self.app_id = None
            if app_id is not None:
                self.apps.pop(app_id, None)
                await self._dispatch("app_disconnect", app_id)

        elif message.type == WStype.MSG:
            await self._on_app_message(message.msg)

        elif message.type == WStype.ERROR:
            # 伺服器會以 403 回應客戶端發送的 heartbeat，不影響連線
            logger.debug(f"Server error: {message.msg}")

    async def _on_app_paired(self, app_id: str) -> None:
        self.app_id = app_id
        app = self._add_app(app_id)
        app.replace_devices(
            [
                {
                    "slotId": self.SLOT_ID,
                    "name": "Coyote",
                    "type": DeviceType.COYOTE_030,
                    "slotState": {"hasDevice": True},
                }
            ]
        )
        await self._dispatch("app_connect", app_id)
        await self._dispatch("devices", list(app), app_id)

    async def _on_app_message(self, msg: Optional[str]) -> None:
        if msg is None:
            logger.warning("Received message with None content")
            return
        app = self.apps.get(self.app_id) if self.app_id else None

        if msg.startswith("feedback"):
            button = WSMessage({"type": "msg", "message": msg}).feedback()
            await self._dispatch("button", button)
            await self._dispatch("action", int(button), self.app_id)

        elif msg.startswith("strength"):
            strength = WSMessage({"type": "msg", "message": msg}).strength()
            device = app.get_device(self.SLOT_ID) if app else None
            if app is None or device is None:
                return
            before = self._strength_snapshots(app)
            device.apply_patch(
                {"intensityA": strength.A, "intensityB": strength.B},
                {"channelA": {"intensityMax": strength.MAXA}, "channelB": {"intensityMax": strength.MAXB}},
            )
            await self._dispatch("device", device, app.client_id)
            await self._dispatch_strength_changes(app, before)

        else:
            logger.warning(f"Unknown message type: {msg}")

    async def _heartbeat(self) -> None:
        try:
            while True:
                await self._send_frame({"type": "heartbeat", "clientId": self.target_id, "message": "200"})
                if self.app_id is None:
                    self._disconnect_count += 1
                    if self._disconnect_count >= self.disconnect_time:
                        logger.error("Disconnected from app")
                        if self.ws:
                            await self.ws.close()
                        return
                else:
                    self._disconnect_count = 0
                await asyncio.sleep(self.interval)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Heartbeat error: {e}")

    async def _send(self, message: dict) -> None:
        message.update({"clientId": self.target_id, "targetId": self.app_id})
        await self._send_frame(message)

    async def _send_strength(self, channel: Channel, mode: StrengthMode, value: int) -> None:
        await self._send({"type": StrengthType.SPECIFIC, "message": f"strength-{int(channel)}+{int(mode)}+{value}"})

    async def add_strength(self, device: Device, channel: Channel, value: int, **options: Any) -> None:
        mode = StrengthMode.INCREASE if value >= 0 else StrengthMode.DECREASE
        await self._send_strength(channel, mode, abs(value))

    async def reset_strength(self, device: Device, channel: Channel, **options: Any) -> None:
        await self._send_strength(channel, StrengthMode.SPECIFIC, 0)

    async def set_strength(self, device: Device, channel: Channel, value: int) -> None:
        await self._send_strength(channel, StrengthMode.SPECIFIC, value)

    async def set_temp_strength(
        self, device: Device, channel: Channel, value: int, duration: int, **options: Any
    ) -> None:
        raise NotSupportedError("V3 protocol does not support temporary strength")

    async def send_pulse(
        self, device: Device, channel: Channel, frames: list[str], duration: int, **options: Any
    ) -> None:
        time = math.ceil(duration / 1000) if duration > 0 else math.ceil(len(frames) / 10)
        await self.send_wave(device, channel, frames, max(1, time))

    async def send_wave(self, device: Device, channel: Channel, frames: list[str], time: int, **options: Any) -> None:
        if len(frames) <= 4:
            frames = frames * 2
        ch = "A" if channel == Channel.A else "B"
        await self._send(
            {
                "type": MessageType.CLIENT_MSG,
                "channel": ch,
                "message": f"{ch}:{json.dumps(frames)}",
                "time": time,
            }
        )

    async def clear(self, device: Device, channel: Channel) -> None:
        for ch in split_channel(channel):
            await self._send({"type": "msg", "message": f"clear-{int(ch)}"})

    async def clear_all(self, app: App) -> None:
        for device in app:
            if isinstance(device, OutputDevice):
                await self.clear(device, Channel.BOTH)

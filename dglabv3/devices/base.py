from typing import TYPE_CHECKING, Any, Iterator, Optional

from dglabv3.dtype import Channel, Strength
from dglabv3.waves import to_hex_frames

if TYPE_CHECKING:
    from dglabv3.devices.registry import DeviceRegistry
    from dglabv3.protocols.base import Protocol

FRAME_INTERVAL_MS = 100


def merge_patch(current: Any, patch: Any) -> Any:
    if not isinstance(current, dict) or not isinstance(patch, dict):
        return patch
    merged = dict(current)
    for key, value in patch.items():
        merged[key] = merge_patch(current.get(key), value)
    return merged


def split_channel(channel: Channel) -> list[Channel]:
    if channel == Channel.BOTH:
        return [Channel.A, Channel.B]
    if channel in (Channel.A, Channel.B):
        return [channel]
    raise ValueError(f"Invalid channel: {channel}")


class Device:
    def __init__(
        self,
        app: "App",
        slot_id: str,
        name: str = "",
        type: str = "",
        props: Optional[dict] = None,
        slot_state: Optional[dict] = None,
    ) -> None:
        self.app = app
        self.slot_id = slot_id
        self.name = name
        self.type = type
        self.props: dict = dict(props or {})
        self.slot_state: dict = dict(slot_state or {})

    def __repr__(self) -> str:
        return f"<{type(self).__name__} slot_id={self.slot_id!r} name={self.name!r} type={self.type!r}>"

    @property
    def protocol(self) -> "Protocol":
        return self.app.protocol

    @property
    def client_id(self) -> str:
        """所屬 App 的 ID"""
        return self.app.client_id

    @property
    def has_device(self) -> bool:
        """設備是否已藍牙連接"""
        return bool(self.slot_state.get("hasDevice", False))

    @property
    def power(self) -> Optional[int]:
        """電量 0-100"""
        return self.props.get("power")

    @property
    def mark_light(self) -> Optional[str]:
        """設備燈顏色"""
        return self.slot_state.get("markLight")

    def apply_patch(self, props: Optional[dict] = None, slot_state: Optional[dict] = None) -> None:
        """
        合併增量資料
        """
        if props:
            self.props = merge_patch(self.props, props)
        if slot_state:
            self.slot_state = merge_patch(self.slot_state, slot_state)


class OutputDevice(Device):
    def get_strength(self, channel: Channel) -> Optional[int]:
        """
        取得通道當前強度，BOTH 時返回較小值

        :return: 強度，未知時返回 None
        """
        values = [self.props.get("intensityA" if ch == Channel.A else "intensityB") for ch in split_channel(channel)]
        known = [v for v in values if v is not None]
        return min(known) if known else None

    def get_max_strength(self, channel: Channel) -> Optional[int]:
        """
        取得通道強度上限，BOTH 時返回較小值

        :return: 強度上限，未知時返回 None
        """
        values = []
        for ch in split_channel(channel):
            state = self.slot_state.get("channelA" if ch == Channel.A else "channelB")
            if isinstance(state, dict) and state.get("intensityMax") is not None:
                values.append(state["intensityMax"])
        return min(values) if values else None

    def is_muted(self, channel: Channel) -> bool:
        """通道是否靜音"""
        state = self.slot_state.get("channelA" if channel == Channel.A else "channelB")
        return bool(isinstance(state, dict) and state.get("isMuted"))

    def strength_snapshot(self) -> Optional[Strength]:
        """
        取得強度快照，強度未知時返回 None
        """
        a = self.get_strength(Channel.A)
        b = self.get_strength(Channel.B)
        if a is None and b is None:
            return None
        max_a = self.get_max_strength(Channel.A)
        max_b = self.get_max_strength(Channel.B)
        return Strength(
            A=a or 0,
            B=b or 0,
            MAXA=200 if max_a is None else max_a,
            MAXB=200 if max_b is None else max_b,
            client_id=self.client_id,
            slot_id=self.slot_id,
        )

    async def _each(self, channel: Channel, call) -> Any:
        results = [await call(ch) for ch in split_channel(channel)]
        return results[0] if len(results) == 1 else results

    async def add_strength(self, channel: Channel, value: int, **options: Any) -> Any:
        """
        增加通道強度 (負數為減少)

        :param options: wait / priority / immediate (V4)

        Example:

        >>> await device.add_strength(Channel.A, 5)
        """
        return await self._each(channel, lambda ch: self.protocol.add_strength(self, ch, value, **options))

    async def decrease_strength(self, channel: Channel, value: int, **options: Any) -> Any:
        """
        減少通道強度
        """
        return await self.add_strength(channel, -value, **options)

    async def reset_strength(self, channel: Channel, **options: Any) -> Any:
        """
        通道強度歸零
        """
        return await self._each(channel, lambda ch: self.protocol.reset_strength(self, ch, **options))

    async def set_strength(self, channel: Channel, value: int) -> Any:
        """
        設定通道強度

        :raises ValueError: 強度小於0或超過上限
        """
        max_strength = self.get_max_strength(channel)
        if value < 0 or (max_strength is not None and value > max_strength):
            raise ValueError(f"strength must be between 0 and {max_strength}")
        return await self._each(channel, lambda ch: self.protocol.set_strength(self, ch, value))

    async def set_temp_strength(self, channel: Channel, value: int, duration: int, **options: Any) -> Any:
        """
        設定臨時強度，結束後自動歸零 (僅 V4)

        :param duration: 持續時間(毫秒)，0 為不自動結束
        :param options: wait / priority / immediate
        """
        return await self._each(
            channel, lambda ch: self.protocol.set_temp_strength(self, ch, value, duration, **options)
        )

    async def send_pulse(self, channel: Channel, frames: list[str], duration: int = 0, **options: Any) -> Any:
        """
        下發原始16進制波形幀，每幀 100ms

        :param frames: 16進制字串列表
        :param duration: 最長播放時間(毫秒)，0 為播放完所有幀
        :param options: wait / priority / immediate / version (V4)
        """
        return await self._each(channel, lambda ch: self.protocol.send_pulse(self, ch, frames, duration, **options))

    async def send_wave(self, wave, time: int = 10, channel: Channel = Channel.BOTH, **options: Any) -> Any:
        """
        發送波形，波形會重複播放直到 time 秒結束

        :param wave: Pulse() / PULSES 格式或16進制字串列表
        :param time: 持續時間(秒)

        Example:

        >>> await device.send_wave(Pulse().breath, 30, Channel.A)
        """
        frames = to_hex_frames(wave)
        return await self._each(channel, lambda ch: self.protocol.send_wave(self, ch, frames, time, **options))

    async def clear(self, channel: Channel = Channel.BOTH) -> None:
        """
        清除通道上的波形與任務
        """
        await self.protocol.clear(self, channel)


class App:
    def __init__(self, client_id: str, protocol: "Protocol", registry: "DeviceRegistry") -> None:
        self.client_id = client_id
        self.protocol = protocol
        self.registry = registry
        self.devices: dict[str, Device] = {}

    def __repr__(self) -> str:
        return f"<App client_id={self.client_id!r} devices={list(self.devices.values())}>"

    def __iter__(self) -> Iterator[Device]:
        return iter(self.devices.values())

    def get_device(self, slot_id: str) -> Optional[Device]:
        return self.devices.get(slot_id)

    def replace_devices(self, devices: list[dict]) -> None:
        self.devices = {}
        self.patch_devices(devices, [])

    def patch_devices(self, added: list[dict], removed: list[str]) -> None:
        for data in added:
            if isinstance(data, dict) and isinstance(data.get("slotId"), str):
                self.devices[data["slotId"]] = self.registry.create(self, data)
        for slot_id in removed:
            self.devices.pop(slot_id, None)

    def patch_slots(self, slots: list[dict]) -> list[Device]:
        """
        合併 slots.patch

        :return: 有變化的設備列表
        """
        changed = []
        for slot in slots:
            device = self.devices.get(slot.get("slotId"))  # type: ignore[arg-type]
            if device is not None:
                device.apply_patch(slot.get("props"), slot.get("slotState"))
                changed.append(device)
        return changed

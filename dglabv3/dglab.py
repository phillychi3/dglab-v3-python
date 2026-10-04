import asyncio
import inspect
import io
import logging
from typing import Any, Optional, TypeVar, Union, overload

import qrcode

from dglabv3.devices.base import App, Device, OutputDevice
from dglabv3.devices.coyote import Coyote
from dglabv3.devices.registry import DeviceRegistry
from dglabv3.dtype import Channel, StrengthType
from dglabv3.errors import DGLabError
from dglabv3.event import EventEmitter
from dglabv3.protocols.base import Protocol
from dglabv3.protocols.v3 import V3Protocol

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("dglabv3")

D = TypeVar("D", bound=Device)


class dglabv3(EventEmitter):
    """
    DG-LAB 客戶端

    Example:

    >>> client = dglabv3()                     # V3 協議 (舊版 App)
    >>> client = dglabv3(V4Protocol())         # V4 協議 (DG-LAB 4 App)

    Event:
        app_connect(client_id): App 已連接
        app_disconnect(client_id): App 已斷開
        devices(devices, client_id): 設備列表變化
        device(device, client_id): 單一設備狀態變化
        strength(strength): 輸出設備強度變化
        action(action, client_id): App 自定義動作 (V3 為按鈕 1-6，V4 為 0-9)
        button(button): App 按鈕 (僅 V3)
        disconnect(): 與伺服器的連接已斷開

    """

    def __init__(self, protocol: Optional[Protocol] = None, registry: Optional[DeviceRegistry] = None) -> None:
        """
        :param protocol: 通訊協議，預設為 V3Protocol()
        :param registry: 設備註冊表，預設為 DeviceRegistry.default()
        """
        super().__init__()
        self.protocol = protocol or V3Protocol()
        self.registry = registry or DeviceRegistry.default()
        self.protocol.bind(self, self.registry)
        self.bot = None
        self._app_connect_event = asyncio.Event()
        self._device_event = asyncio.Event()

    async def _dispatch(self, name: str, *args: Any) -> None:
        """
        觸發事件，並同步發送給 Discord Bot
        """
        match name:
            case "app_connect":
                self._app_connect_event.set()
            case "devices":
                if args[0]:
                    self._device_event.set()
            case "app_disconnect" | "disconnect":
                if not self.protocol.apps:
                    self._app_connect_event.clear()
                    self._device_event.clear()
        logger.debug(f"Dispatch {name}: {args}")
        self.emit(name, *args)
        if self.bot:
            result = self.bot.dispatch(f"dglab_{name}", *args)
            if inspect.isawaitable(result):
                await result

    def set_bot(self, bot):
        """
        設置Discord Bot

        :param bot: Discord Bot
        """
        self.bot = bot

    @property
    def target_id(self) -> Optional[str]:
        """控制方 ID，App 使用它配對"""
        return self.protocol.target_id

    def is_connected(self) -> bool:
        """
        檢查是否已連接到WebSocket伺服器
        """
        return self.protocol.is_connected()

    def is_linked_to_app(self) -> bool:
        """
        檢查是否已有App連接
        """
        return bool(self.protocol.apps)

    async def connect(self, timeout: float = 30) -> str:
        """
        連接WebSocket並等待綁定完成

        :param timeout: 超時時間(秒)
        :return: 控制方ID
        :raises ConnectionError: 連接失敗
        :raises TimeoutError: 綁定超時
        """
        return await self.protocol.connect(timeout)

    connect_and_wait = connect

    async def wait_for_app_connect(self, timeout: float = 30, wait_device: bool = True) -> App:
        """
        等待App連接

        :param timeout: 超時時間(秒)
        :param wait_device: 是否同時等待App上報設備
        :return: 第一個連接的App
        :raises TimeoutError: App連接超時
        """
        try:
            await asyncio.wait_for(self._app_connect_event.wait(), timeout)
            if wait_device:
                await asyncio.wait_for(self._device_event.wait(), timeout)
        except asyncio.TimeoutError:
            logger.error("App connect timeout")
            await self.close()
            raise TimeoutError("App connect timeout")
        return self.apps[0]

    async def close(self) -> None:
        """
        關閉WebSocket連接並清理資源
        """
        await self.protocol.close()
        self._app_connect_event.clear()
        self._device_event.clear()

    def get_qrcode_url(self) -> Optional[str]:
        """
        取得 App 掃描用的 QR code 內容

        :return: 未連接時返回None
        """
        url = self.protocol.qrcode_url()
        if url is None:
            logger.error("Not connected, please connect to the server first")
        return url

    def generate_qrcode(self) -> Optional[io.BytesIO]:
        """
        生成QR code圖片

        :return: QR code圖片的BytesIO物件，未連接時返回None
        """
        url = self.get_qrcode_url()
        if url is None:
            return None
        qr = qrcode.QRCode()
        qr.add_data(url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        saveimg = io.BytesIO()
        img.save(saveimg)
        saveimg.seek(0)
        return saveimg

    def generate_qrcode_text(self) -> Optional[str]:
        """
        生成QR code文字

        :return: ASCII格式的QR code文字，未連接時返回None
        """
        url = self.get_qrcode_url()
        if url is None:
            return None
        qr = qrcode.QRCode()
        qr.add_data(url)
        f = io.StringIO()
        qr.print_ascii(out=f)
        return f.getvalue()

    @property
    def apps(self) -> list[App]:
        """已連接的App"""
        return list(self.protocol.apps.values())

    @property
    def devices(self) -> list[Device]:
        """所有App的所有設備"""
        return [device for app in self.apps for device in app]

    @overload
    def get_devices(self, kind: type[D]) -> list[D]: ...

    @overload
    def get_devices(self, kind: Union[str, None] = None) -> list[Device]: ...

    def get_devices(self, kind: Any = None) -> list[Any]:
        """
        依照設備類別或類型篩選設備

        :param kind: 設備類別 (Coyote / Ovc / Bmtr) 或 DeviceType，None 為全部

        Example:

        >>> ovcs = client.get_devices(Ovc)
        >>> coyotes = client.get_devices(DeviceType.COYOTE_030)
        """
        if kind is None:
            return self.devices
        if isinstance(kind, type):
            return [d for d in self.devices if isinstance(d, kind)]
        return [d for d in self.devices if d.type == kind]

    @overload
    def get_device(self, kind: type[D], slot_id: Optional[str] = None) -> Optional[D]: ...

    @overload
    def get_device(self, kind: Union[str, None] = None, slot_id: Optional[str] = None) -> Optional[Device]: ...

    def get_device(self, kind: Any = None, slot_id: Optional[str] = None) -> Optional[Any]:
        """
        取得設備，優先返回已藍牙連接的設備

        :param kind: 設備類別或 DeviceType，None 為任意
        :param slot_id: 指定設備ID

        Example:

        >>> ovc = client.get_device(Ovc)
        """
        candidates = [d for d in self.get_devices(kind) if slot_id is None or d.slot_id == slot_id]
        return next((d for d in candidates if d.has_device), next(iter(candidates), None))

    @property
    def device(self) -> OutputDevice:
        """
        預設輸出設備：優先郊狼，其次其他輸出設備

        :raises DGLabError: 沒有可用的輸出設備
        """
        device = self.get_device(Coyote) or self.get_device(OutputDevice)
        if device is None:
            raise DGLabError("No output device available")
        return device

    async def send_wave_message(self, wave, time: int = 10, channel: Channel = Channel.BOTH, **options: Any) -> Any:
        """
        發送波形到預設設備\n

        :param wave: 波形數據 (Pulse() / PULSES 或16進制字串列表)
        :param time: 波形持續時間(秒)
        :param channel: Channel.A or Channel.B or Channel.BOTH

        Example:

        >>> await client.send_wave_message(PULSES["呼吸"], 30, Channel.A)
        """
        return await self.device.send_wave(wave, time, channel, **options)

    async def clear_wave(self, channel: Channel) -> None:
        """
        清除預設設備指定通道的波形

        Example:

        >>> await client.clear_wave(Channel.A)
        """
        await self.device.clear(channel)

    async def clear_all_wave(self) -> bool:
        """
        清除所有App所有設備的波形

        Example:

        >>> await client.clear_all_wave()
        """
        for app in self.apps:
            await self.protocol.clear_all(app)
        return True

    async def set_strength_value(self, channel: Channel, strength: int) -> None:
        """
        設定預設設備通道強度值

        :param strength: 強度值[0-200]

        Example:

        >>> await client.set_strength_value(Channel.A, 50)
        """
        await self.device.set_strength(channel, strength)

    async def add_strength_value(self, channel: Channel, strength: int) -> None:
        """
        增加預設設備通道強度

        Example:

        >>> await client.add_strength_value(Channel.A, 10)
        """
        await self.device.add_strength(channel, strength)

    async def decrease_strength_value(self, channel: Channel, strength: int) -> None:
        """
        減少預設設備通道強度

        Example:

        >>> await client.decrease_strength_value(Channel.A, 5)
        """
        await self.device.decrease_strength(channel, strength)

    async def reset_strength_value(self, channel: Channel) -> None:
        """
        重置預設設備通道強度為0

        Example:

        >>> await client.reset_strength_value(Channel.A)
        """
        await self.device.reset_strength(channel)

    async def set_strength(self, channel: Channel, type_id: StrengthType, strength: int) -> None:
        """
        設定預設設備通道強度

        :param type_id: DECREASE / INCREASE 為減少/增加 1，ZERO 為歸零，SPECIFIC 為指定數值

        Example:

        >>> await client.set_strength(Channel.A, StrengthType.SPECIFIC, 80)
        """
        match type_id:
            case StrengthType.DECREASE:
                await self.decrease_strength_value(channel, 1)
            case StrengthType.INCREASE:
                await self.add_strength_value(channel, 1)
            case StrengthType.ZERO:
                await self.reset_strength_value(channel)
            case StrengthType.SPECIFIC:
                await self.set_strength_value(channel, strength)
            case _:
                logger.error(f"Invalid type id: {type_id}")

    async def set_temp_strength(self, channel: Channel, strength: int, duration: int, **options: Any) -> Any:
        """
        設定預設設備臨時強度，結束後自動歸零 (僅 V4)

        :param duration: 持續時間(毫秒)

        Example:

        >>> await client.set_temp_strength(Channel.A, 30, 3000)
        """
        return await self.device.set_temp_strength(channel, strength, duration, **options)

    def get_strength_value(self, channel: Channel) -> int:
        """
        獲取預設設備通道強度

        Example:

        >>> strength = client.get_strength_value(Channel.A)
        """
        value = self.device.get_strength(channel)
        return 0 if value is None else value

    def get_max_strength_value(self, channel: Channel) -> int:
        """
        獲取預設設備通道最大強度

        Example:

        >>> max_strength = client.get_max_strength_value(Channel.A)
        """
        value = self.device.get_max_strength(channel)
        return 200 if value is None else value

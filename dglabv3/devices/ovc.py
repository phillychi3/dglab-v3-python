from enum import IntEnum
from typing import Optional

from dglabv3.devices.base import OutputDevice
from dglabv3.dtype import Channel


class OvcMode(IntEnum):
    OFF = 0  # 關閉所有上報
    OMS = 1
    HID = 2
    IOS_PAGER = 3  # iOS 翻頁器


class Ovc(OutputDevice):
    """負鼠"""

    def has_accessory(self, channel: Channel) -> bool:
        """
        通道是否插入配件
        """
        return bool(self.props.get("channelAStatus" if channel == Channel.A else "channelBStatus"))

    @property
    def mode(self) -> Optional[OvcMode]:
        value = self.props.get("mode")
        return None if value is None else OvcMode(value)

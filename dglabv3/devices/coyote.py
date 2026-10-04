from enum import IntEnum
from typing import Optional

from dglabv3.devices.base import OutputDevice
from dglabv3.dtype import Channel


class CoyoteChannelStatus(IntEnum):
    """郊狼 V3 通道輸出狀態"""

    NO_OUTPUT = 0  # 無輸出/輸出過低無法檢測
    OPEN_CIRCUIT = 1  # 未形成迴路
    NORMAL = 2  # 輸出正常
    DAMAGED = 3  # 輸出損壞
    BLOCKED = 4  # 通道屏蔽


class Coyote(OutputDevice):
    """郊狼"""

    def channel_status(self, channel: Channel) -> Optional[CoyoteChannelStatus]:
        """
        通道輸出狀態 (僅 Coyote v3)
        """
        value = self.props.get("channelAStatus" if channel == Channel.A else "channelBStatus")
        return None if value is None else CoyoteChannelStatus(value)

    def comfort_limit(self, channel: Channel) -> dict:
        """
        通道舒適強度限制設定 (comfortMax、absoluteMax、overheat 等)
        """
        state = self.slot_state.get("channelA" if channel == Channel.A else "channelB") or {}
        return dict(state.get("comfortLimit") or {})

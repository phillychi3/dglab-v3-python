from enum import Enum, IntEnum
from typing import Final
from dataclasses import dataclass, field

__all__ = ["ChannelStrength", "StrengthType", "StrengthMode", "MessageType", "Channel"]


class Channel(IntEnum):
    A = 1
    B = 2
    BOTH = 3


MAX_STRENGTH: Final[int] = 200
MIN_STRENGTH: Final[int] = 0


@dataclass
class ChannelStrength:
    _A: int = field(default=0, init=False)
    _B: int = field(default=0, init=False)

    def __post_init__(self):
        self.A = self._A
        self.B = self._B

    @property
    def A(self):
        return self._A

    @A.setter
    def A(self, value):
        if value > MAX_STRENGTH:
            raise ValueError("stronger A cannot be greater than 200")
        if value < MIN_STRENGTH:
            raise ValueError("stronger A cannot be less than 0")
        self._A = value

    @property
    def B(self):
        return self._B

    @B.setter
    def B(self, value):
        if value > MAX_STRENGTH:
            raise ValueError("stronger B cannot be greater than 200")
        if value < MIN_STRENGTH:
            raise ValueError("stronger B cannot be less than 0")
        self._B = value


# 強度調整類型
class StrengthType(IntEnum):
    """
    屬性:
        DECREASE: 通道強度減少
        INCREASE: 通道強度增加
        ZERO: 通道強度歸零
        SPECIFIC: 通道強度指定為某個值
    """

    DECREASE = 1  # 通道強度減少
    INCREASE = 2  # 通道強度增加
    ZERO = 3  # 通道強度歸零
    SPECIFIC = 4  # 通道強度指定為某個值


# 強度變化模式（用於 type 4）
class StrengthMode(IntEnum):
    """
    屬性:
        DECREASE: 通道強度減少
        INCREASE: 通道強度增加
        SPECIFIC: 通道強度變化為指定數值
    """

    DECREASE = 0  # 通道強度減少
    INCREASE = 1  # 通道強度增加
    SPECIFIC = 2  # 通道強度變化為指定數值


class MessageType(str, Enum):
    SET_CHANNEL = "set channel"
    HEARTBEAT = "heartbeat"
    BIND = "bind"
    CLIENT_MSG = "clientMsg"
    MSG = "msg"

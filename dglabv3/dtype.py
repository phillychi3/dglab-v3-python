from enum import Enum, IntEnum, StrEnum
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
class Strength:
    A: int
    B: int
    MAXA: int
    MAXB: int


@dataclass
class ChannelStrength:
    _A: int = field(default=0, init=False)
    _B: int = field(default=0, init=False)
    _MAX_A: int = field(default=MAX_STRENGTH, init=False)
    _MAX_B: int = field(default=MAX_STRENGTH, init=False)

    def __post_init__(self):
        self.A = self._A
        self.B = self._B
        self.MAX_A = self._MAX_A
        self.MAX_B = self._MAX_B

    @property
    def A(self):
        return self._A

    @property
    def MAX_A(self):
        return self._MAX_A

    @A.setter
    def A(self, value):
        if value > self.MAX_A:
            raise ValueError(f"stronger A cannot be greater than {self.MAX_A}")
        if value < MIN_STRENGTH:
            raise ValueError("stronger A cannot be less than 0")
        self._A = value

    @MAX_A.setter
    def MAX_A(self, value):
        if value < 0:
            raise ValueError("MAX_A cannot be less than 0")
        self._MAX_A = value

    @property
    def B(self):
        return self._B

    @property
    def MAX_B(self):
        return self._MAX_B

    @B.setter
    def B(self, value):
        if value > self.MAX_B:
            raise ValueError(f"stronger B cannot be greater than {self.MAX_B}")
        if value < MIN_STRENGTH:
            raise ValueError("stronger B cannot be less than 0")
        self._B = value

    @MAX_B.setter
    def MAX_B(self, value):
        if value < 0:
            raise ValueError("MAX_B cannot be less than 0")
        self._MAX_B = value

    def set_strength(self, strength: Strength):
        self.MAX_A = strength.MAXA
        self.MAX_B = strength.MAXB
        self.A = strength.A
        self.B = strength.B


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


class Button(StrEnum):
    button_1 = "1"
    button_2 = "2"
    button_3 = "3"
    button_4 = "4"
    button_5 = "5"
    button_6 = "6"

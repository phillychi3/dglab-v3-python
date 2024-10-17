from enum import Enum, IntEnum
from typing import Final

# 通道定義
class Channel(IntEnum):
    A = 1
    B = 2
    BOTH = 3

# 強度調整類型
class StrengthType(IntEnum):
    DECREASE = 1  # 通道強度減少
    INCREASE = 2  # 通道強度增加
    ZERO = 3      # 通道強度歸零
    SPECIFIC = 4  # 通道強度指定為某個值

# 強度變化模式（用於 type 4）
class StrengthMode(IntEnum):
    DECREASE = 0  # 通道強度減少
    INCREASE = 1  # 通道強度增加
    SPECIFIC = 2  # 通道強度變化為指定數值



MAX_STRENGTH: Final[int] = 200
MIN_STRENGTH: Final[int] = 0


class MessageType(str, Enum):
    SET_CHANNEL = "set channel"
    HEARTBEAT = "heartbeat"
    BIND = "bind"
    CLIENT_MSG = "clientMsg"
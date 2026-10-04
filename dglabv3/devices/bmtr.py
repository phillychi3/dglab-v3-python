from enum import IntEnum
from typing import Optional

from dglabv3.devices.base import Device


class EdgeState(IntEnum):
    STOPPED = 0  # 停止
    STIMULATING = 1  # 刺激狀態
    COOLDOWN_TIMER = 2  # 強制冷靜最小時間計時
    COOLDOWN_PRESSURE = 3  # 強制冷靜並判斷氣壓低於藍線
    ALLOWED = 4  # 允許起飛


class Bmtr(Device):
    """
    靈貓
    """

    @property
    def pressure(self) -> Optional[float]:
        """當前壓力值"""
        return self.props.get("pressure")

    @property
    def edge_state(self) -> Optional[EdgeState]:
        """邊控狀態"""
        edge = self.slot_state.get("edge") or {}
        value = edge.get("edgeState")
        return None if value is None else EdgeState(value)

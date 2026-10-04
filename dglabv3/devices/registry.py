from typing import TYPE_CHECKING, Optional

from dglabv3.devices.base import Device
from dglabv3.devices.bmtr import Bmtr
from dglabv3.devices.coyote import Coyote
from dglabv3.devices.ovc import Ovc
from dglabv3.dtype import DeviceType

if TYPE_CHECKING:
    from dglabv3.devices.base import App


class DeviceRegistry:
    def __init__(self, mapping: Optional[dict[str, type[Device]]] = None, fallback: type[Device] = Device) -> None:
        self._mapping: dict[str, type[Device]] = dict(mapping or {})
        self.fallback = fallback

    @classmethod
    def default(cls) -> "DeviceRegistry":
        return cls(
            {
                DeviceType.COYOTE_020: Coyote,
                DeviceType.COYOTE_030: Coyote,
                DeviceType.OVC_1: Ovc,
                DeviceType.BMTR_1: Bmtr,
            }
        )

    def register(self, device_type: str, device_class: type[Device]) -> "DeviceRegistry":
        self._mapping[str(device_type)] = device_class
        return self

    def get_class(self, device_type: str) -> type[Device]:
        return self._mapping.get(device_type, self.fallback)

    def create(self, app: "App", data: dict) -> Device:
        device_type = data.get("type") or ""
        return self.get_class(device_type)(
            app,
            slot_id=data["slotId"],
            name=data.get("name") or "",
            type=device_type,
            props=data.get("props"),
            slot_state=data.get("slotState"),
        )

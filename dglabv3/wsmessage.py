from enum import Enum
from typing import Optional
from dglabv3.dtype import Button, Strength


class WStype(Enum):
    MSG = "msg"
    HEARTBEAT = "heartbeat"
    BIND = "bind"
    BREAK = "break"
    ERROR = "error"





class WSMessage:
    def __init__(self, data: dict):
        self.type: WStype = WStype(data.get("type"))
        self.msg: Optional[dict] = data.get("message", None)
        self.targetID: Optional[str] = data.get("targetId", None)
        self.clientID: Optional[str] = data.get("clientId", None)

    def to_dict(self) -> dict:
        return {
            key: value
            for key, value in {
                "type": self.type.value,
                "msg": self.msg,
                "targetId": self.targetID,
                "clientId": self.clientID,
            }.items()
            if value is not None
        }

    def feedback(self) -> Button:
        return Button(self.msg.split("-")[1])

    def strength(self) -> Strength:
        splitmsg = self.msg.split("-")[1].split("+")
        return Strength(A=int(splitmsg[0]), B=int(splitmsg[1]), MAXA=int(splitmsg[2]), MAXB=int(splitmsg[3]))

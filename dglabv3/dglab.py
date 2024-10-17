import websocket
import json
import logging
import qrcode
import threading
import io
from threading import Event
import asyncio
from type import (
    Channel,
    StrengthType,
    StrengthMode,
    MessageType,
    MAX_STRENGTH,
    MIN_STRENGTH,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class dglabv3:
    def __init__(self) -> None:
        self.client = None
        self.clienturl = "wss://ws.dungeon-lab.cn/"
        self.client_id = None
        self.connects: dict[str, str] = {}
        self.heartbeat_interval = None
        self.pulse_name = None
        self.clientqrurl = "https://www.dungeon-lab.com/app-download.php#DGLAB-SOCKET#wss://ws.dungeon-lab.cn/"
        self.strength = 0
        self.interval = 20
        self.maxInterval = 50
        self._bind_event = Event()

    async def connect_and_wait(self) -> None:
        """連接並等待bind完成"""
        self.connect()
        await asyncio.get_event_loop().run_in_executor(None, self._bind_event.wait)

    def connect(self) -> None:
        def on_message(ws, message):
            self._handle_message(message)

        def on_error(ws, error):
            logger.error(f"WebSocket connection error: {error}")
            self.close()

        def on_close(ws, close_status_code, close_msg):
            logger.info("WebSocket connection closed")
            self.stop_heartbeat()

        def on_open(ws):
            logger.info("WebSocket connected")

        self.client = websocket.WebSocketApp(
            self.clienturl,
            on_message=on_message,
            on_error=on_error,
            on_close=on_close,
            on_open=on_open,
        )

        wst = threading.Thread(target=self.client.run_forever)
        wst.daemon = True
        wst.start()

    def generate_qrcode(self) -> io.BytesIO:
        if self.client_id is None:
            logger.error("Client ID is empty, please connect to the server first")
            return
        qr = qrcode.QRCode()
        qr.add_data(self.clientqrurl + self.client_id)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        saveimg = io.BytesIO()
        img.save(saveimg, format="PNG")
        saveimg.seek(0)
        return saveimg

    def generate_qrcode_text(self) -> str:
        print("im in")
        if self.client_id is None:
            logger.error("Client ID is empty, please connect to the server first")
            return
        qr = qrcode.QRCode()
        qr.add_data(self.clientqrurl + self.client_id)
        f = io.StringIO()
        qr.print_ascii(out=f)
        return f.getvalue()

    def update_connects(self, message: dict):
        if message["targetId"]:
            self.connects[message["clientId"]] = message["targetId"]
            self.set_strength(1, 4, self.strength)
            self.set_strength(2, 4, self.strength)

    def start_heartbeat(self):
        def heartbeat():
            if self.client and self.client.sock and self.client.sock.connected:
                self.send_message(
                    {"type": "heartbeat", "clientId": self.client_id, "message": "200"}
                )
                self.set_strength(1, 4, self.interval)
                self.set_strength(2, 4, self.interval)
            else:
                logger.error("WebSocket not connected")

        self.heartbeat_interval = threading.Timer(self.interval, heartbeat)
        self.heartbeat_interval.start()

    def _stop_heartbeat(self):
        if self.heartbeat_interval:
            self.heartbeat_interval.cancel()
            self.heartbeat_interval = None
            logger.info("Heartbeat stopped")

    def _handle_message(self, data: str):
        try:
            message = json.loads(data)

            if message.get("type") == "bind":
                self.client_id = message["clientId"]
                self.start_heartbeat()
                self.update_connects(message)
                self._bind_event.set()

            logger.info(f"Received message: {message}")
        except Exception as e:
            logger.info(f"Received raw message: {data}")
            logger.error(f"Error parsing message: {e}")

    def send_message(self, message: dict):
        if self.client and self.client.sock and self.client.sock.connected:
            self.client.send(json.dumps(message))
            logger.info(f"Sent message: {json.dumps(message)}")
        else:
            logger.error("WebSocket not connected")

    def close(self):
        if self.client:
            self.client.close()
            logger.info("WebSocket closed")
        self._stop_heartbeat()
        if self.client_id in self.connects:
            del self.connects[self.client_id]

    async def send_wave_message(self, wave, time: int, channel: Channel = None):
        if channel == 1:
            channel = "A"
        elif channel == 2:
            channel = "B"
        elif channel == 3:
            channel = "BOTH"

        def _create_wave_message(
            client_id: str, target_id: str, channel: Channel, wave, time: int
        ) -> dict:
            return {
                "type": MessageType.CLIENT_MSG,
                "channel": channel,
                "clientId": client_id,
                "targetId": target_id,
                "message": f"{channel}:{json.dumps(wave)}",
                "time": time,
            }

        for client_id, target_id in self.connects.items():
            # type : clientMsg 固定不变
            # message : A通道波形数据(16进制HEX数组json,具体见上面的协议说明)
            # message2 : B通道波形数据(16进制HEX数组json,具体见上面的协议说明)
            # time1 : A通道波形数据持续发送时长
            # time2 : B通道波形数据持续发送时长
            if channel == "BOTH":
                for ch in ["A", "B"]:
                    message = _create_wave_message(client_id, target_id, ch, wave, time)
                    self.send_message(message)
            else:
                message = _create_wave_message(
                    client_id, target_id, channel, wave, time
                )
                self.send_message(message)

    def clear_all_wave(self):
        for client_id, target_id in self.connects.items():
            # type : msg 固定不变
            # message: clear-1 -> 清除A通道波形队列; clear-2 -> 清除B通道波形队列
            self.send_message(
                {
                    "type": 4,
                    "clientId": client_id,
                    "targetId": target_id,
                    "message": "clear-1",
                }
            )
            self.send_message(
                {
                    "type": 4,
                    "clientId": client_id,
                    "targetId": target_id,
                    "message": "clear-2",
                }
            )
        logger.info("Cleared all waves")
        return True

    def set_strength(
        self, channel: Channel, type_id: StrengthType, strength: int
    ) -> None:
        if strength < MIN_STRENGTH or strength > MAX_STRENGTH:
            logger.error(
                f"Invalid strength value. Must be between {MIN_STRENGTH} and {MAX_STRENGTH}"
            )
            return

        for client_id, target_id in self.connects.items():
            # type : 1 -> 通道强度减少; 2 -> 通道强度增加; 3 -> 通道强度归零 ;4 -> 通道强度指定为某个值
            # strength: 强度值变化量/指定强度值(当type为1或2时，该值会被强制设置为1)
            # message: 'set channel' 固定不变
            if type_id in [
                StrengthType.DECREASE,
                StrengthType.INCREASE,
                StrengthType.ZERO,
            ]:
                # 當type為DECREASE或INCREASE時，強度值強制設為1
                if type_id in [StrengthType.DECREASE, StrengthType.INCREASE]:
                    strength = 1

                self.send_message(
                    {
                        "type": type_id,
                        "channel": channel,
                        "clientId": client_id,
                        "targetId": target_id,
                        "strength": strength,
                        "message": MessageType.SET_CHANNEL,
                    }
                )

            elif type_id == StrengthType.SPECIFIC:
                self.send_message(
                    {
                        "type": type_id,
                        "clientId": client_id,
                        "targetId": target_id,
                        "message": f"strength-{channel}+{StrengthMode.SPECIFIC}+{strength}",
                    }
                )

            else:
                logger.error(f"Invalid type id: {type_id}")
                return


if __name__ == "__main__":

    async def main():
        client = dglabv3()

        try:
            await client.connect_and_wait()
            qr_code = client.generate_qrcode_text()
            print(qr_code)

        except Exception as e:
            logger.error(f"Error: {e}")
            client.close()

    asyncio.run(main())
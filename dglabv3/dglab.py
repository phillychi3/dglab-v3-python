import websocket
import json
import logging
import qrcode
import threading
import io
from threading import Event
import asyncio
from dglabv3.dtype import (
    Channel,
    StrengthType,
    StrengthMode,
    MessageType,
    ChannelStrength,
)

logging.basicConfig(level=logging.WARN)
logger = logging.getLogger("dglabv3")


class dglabv3:
    def __init__(self) -> None:
        self.client = None
        self.clienturl = "wss://ws.dungeon-lab.cn/"
        self.client_id = None
        self.target_id = None
        self.heartbeat_interval = None
        self.pulse_name = None
        self.clientqrurl = "https://www.dungeon-lab.com/app-download.php#DGLAB-SOCKET#wss://ws.dungeon-lab.cn/"
        self.interval = 20
        self.maxInterval = 50
        self.strength = ChannelStrength()
        self._bind_event = Event()
        self._app_connect_event = Event()

    def is_connected(self) -> bool:
        return self.client and self.client.sock and self.client.sock.connected

    def is_linked_to_app(self) -> bool:
        return self.client_id is not None

    async def connect_and_wait(self, timeout: int = 30) -> None:
        """
        連接並等待bind完成
        """
        self.connect()
        try:
            await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(None, self._bind_event.wait),
                timeout,
            )
        except asyncio.TimeoutError:
            logger.error("Bind timeout")
            raise TimeoutError("Bind timeout")

    async def wait_for_app_connect(self, timeout: int = 30) -> None:
        """
        等待app連結
        """
        try:
            await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(None, self._app_connect_event.wait),
                timeout,
            )
        except asyncio.TimeoutError:
            logger.error("App connect timeout")
            raise TimeoutError("App connect timeout")

    def connect(self) -> None:
        """
        連接到websocket服務器
        """

        def on_message(ws, message):
            self._handle_message(message)

        def on_error(ws, error):
            logger.error(f"WebSocket connection error: {error}")
            self.close()

        def on_close(ws, close_status_code, close_msg):
            logger.info("WebSocket connection closed")
            self._stop_heartbeat()

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
        """
        生成QR code圖片
        """
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
        """
        生成QR code文字
        """
        if self.client_id is None:
            logger.error("Client ID is empty, please connect to the server first")
            return
        qr = qrcode.QRCode()
        qr.add_data(self.clientqrurl + self.client_id)
        f = io.StringIO()
        qr.print_ascii(out=f)
        return f.getvalue()

    def _update_connects(self, message: dict):
        if message["targetId"] and message["targetId"] != "":
            self.target_id = message["targetId"]
            self.set_strength(Channel.A, StrengthType.SPECIFIC, self.strength.A)
            self.set_strength(Channel.B, StrengthType.SPECIFIC, self.strength.B)
            self._app_connect_event.set()

    def _start_heartbeat(self):
        def heartbeat():
            if self.client and self.client.sock and self.client.sock.connected:
                self._send_message(
                    {"type": "heartbeat", "clientId": self.client_id, "message": "200"},
                    update=False,
                )
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
                self._start_heartbeat()
                self._update_connects(message)
                self._bind_event.set()

            logger.info(f"Received message: {message}")
        except Exception as _:
            logger.info(f"Received raw message: {data}")

    def _send_message(self, message: dict, update=True):
        if self.client and self.client.sock and self.client.sock.connected:
            if update:
                dict.update(message, {"clientId": self.client_id, "targetId": self.target_id})
            self.client.send(json.dumps(message))
            logger.info(f"Sent message: {json.dumps(message)}")
        else:
            logger.error("WebSocket not connected")

    def close(self):
        """
        斷開連結
        """
        if self.client:
            self.client.close()
            logger.info("WebSocket closed")
        self._stop_heartbeat()
        self._app_connect_event.clear()
        self._bind_event.clear()

    @staticmethod
    def _wave2hex(data):
        return ["".join(format(num, "02X") for num in sum(item, [])) for item in data]

    def send_wave_message(self, wave, time: int = 10, channel: Channel = Channel.BOTH):
        """
        發送波形\n
        wave: Pulse().breath\n
        time: 30\n
        channel: Channel.A
        """
        if channel == 1:
            channel = "A"
        elif channel == 2:
            channel = "B"
        elif channel == 3:
            channel = "BOTH"

        def _create_wave_message(channel: str, wave, time: int) -> dict:
            return {
                "type": MessageType.CLIENT_MSG,
                "channel": channel,
                "message": f"{channel}:{json.dumps(self._wave2hex(wave))}",
                "time": time,
            }

        # type : clientMsg 固定不变
        # message : A通道波形数据(16进制HEX数组json,具体见上面的协议说明)
        # message2 : B通道波形数据(16进制HEX数组json,具体见上面的协议说明)
        # time1 : A通道波形数据持续发送时长
        # time2 : B通道波形数据持续发送时长
        if channel == "BOTH":
            for ch in ["A", "B"]:
                message = _create_wave_message(ch, wave, time)
                self._send_message(message)
        else:
            message = _create_wave_message(channel, wave, time)
            self._send_message(message)

    def clear_wave(self, channel: Channel):
        if channel == Channel.A:
            self._send_message(
                {
                    "type": "msg",
                    "message": "clear-1",
                }
            )
        elif channel == Channel.B:
            self._send_message(
                {
                    "type": "msg",
                    "message": "clear-2",
                }
            )
        elif channel == Channel.BOTH:
            self._send_message(
                {
                    "type": "msg",
                    "message": "clear-1",
                }
            )
            self._send_message(
                {
                    "type": "msg",
                    "message": "clear-2",
                }
            )
        else:
            logger.error(f"Invalid channel: {channel}")

    def clear_all_wave(self):
        # type : msg 固定不变
        # message: clear-1 -> 清除A通道波形队列; clear-2 -> 清除B通道波形队列
        self._send_message(
            {
                "type": "msg",
                "message": "clear-1",
            }
        )
        self._send_message(
            {
                "type": "msg",
                "message": "clear-2",
            }
        )
        logger.info("Cleared all waves")
        return True

    def set_strength_value(self, channel: Channel, strength: int) -> None:
        """
        设置通道强度
        """
        self.set_strength(channel, StrengthType.SPECIFIC, strength)

    def add_strength_value(self, channel: Channel, strength: int) -> None:
        """
        增加通道強度
        """
        if channel == Channel.BOTH:
            self.add_strength_value(Channel.A, strength)
            self.add_strength_value(Channel.B, strength)
            return
        now_strength = self.strength.A if channel == Channel.A else self.strength.B
        self.set_strength(channel, StrengthType.SPECIFIC, now_strength + strength)

    def decrease_strength_value(self, channel: Channel, strength: int) -> None:
        """
        減少通道強度
        """
        if channel == Channel.BOTH:
            self.decrease_strength_value(Channel.A, strength)
            self.decrease_strength_value(Channel.B, strength)
            return
        now_strength = self.strength.A if channel == Channel.A else self.strength.B
        self.set_strength(channel, StrengthType.SPECIFIC, now_strength - strength)

    def reset_strength_value(self, channel: Channel) -> None:
        """
        通道強度重置為0
        """
        self.set_strength(channel, StrengthType.ZERO, 0)

    def set_strength(self, channel: Channel, type_id: StrengthType, strength: int) -> None:
        """
        channel: 通道
        type_id: StrengthType
        strength: 強度值[0-200]
        """
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

            if channel == Channel.BOTH:
                self._send_message(
                    {
                        "type": type_id,
                        "channel": Channel.A,
                        "strength": strength,
                        "message": MessageType.SET_CHANNEL,
                    }
                )
                self._send_message(
                    {
                        "type": type_id,
                        "channel": Channel.B,
                        "strength": strength,
                        "message": MessageType.SET_CHANNEL,
                    }
                )
            else:
                self._send_message(
                    {
                        "type": type_id,
                        "channel": channel,
                        "strength": strength,
                        "message": MessageType.SET_CHANNEL,
                    }
                )

        elif type_id == StrengthType.SPECIFIC:
            if channel == Channel.BOTH:
                self.strength.A = strength
                self.strength.B = strength
                self._send_message(
                    {
                        "type": type_id,
                        "message": f"strength-{Channel.A}+{StrengthMode.SPECIFIC}+{self.strength.A}",
                    }
                )
                self._send_message(
                    {
                        "type": type_id,
                        "message": f"strength-{Channel.B}+{StrengthMode.SPECIFIC}+{self.strength.B}",
                    }
                )
            else:
                if channel == Channel.A:
                    self.strength.A = strength
                    self._send_message(
                        {
                            "type": type_id,
                            "message": f"strength-{channel}+{StrengthMode.SPECIFIC}+{self.strength.A}",
                        }
                    )
                elif channel == Channel.B:
                    self.strength.B = strength
                    self._send_message(
                        {
                            "type": type_id,
                            "message": f"strength-{channel}+{StrengthMode.SPECIFIC}+{self.strength.B}",
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

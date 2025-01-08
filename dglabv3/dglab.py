import json
import logging
import qrcode
import io
import asyncio
from threading import Event
from websockets.asyncio.client import connect as ws_connect
import websockets
from dglabv3.dtype import Button, Channel, StrengthType, StrengthMode, MessageType, ChannelStrength, Strength
from dglabv3.wsmessage import WSMessage, WStype
from dglabv3.event import EventEmitter

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("dglabv3")


class dglabv3(EventEmitter):
    def __init__(self) -> None:
        super().__init__()
        self.client = None
        self.clienturl = "wss://ws.dungeon-lab.cn/"
        self.client_id = None
        self.target_id = None
        self.pulse_name = None
        self.clientqrurl = "https://www.dungeon-lab.com/app-download.php#DGLAB-SOCKET#wss://ws.dungeon-lab.cn/"
        self.interval = 20
        self.maxInterval = 50
        self.disconnect_time = 30
        self.strength = ChannelStrength()
        self._bind_event = Event()
        self._app_connect_event = Event()
        self._disconnect_count = 0
        self._heartbeat_task = None
        self._listen_task = None
        self._closing = False

    async def _dispatch_button(self, button: Button) -> None:
        self.emit("button", button)

    async def _dispatch_strength(self, strength: Strength) -> None:
        logger.debug(f"Dispatch strength: {strength}")
        self.emit("strength", strength)

    def is_connected(self) -> bool:
        """
        是否連接到WebSocket
        """
        return self.client and self.client.sock and self.client.sock.connected

    def is_linked_to_app(self) -> bool:
        """
        是否連接到app
        """
        return self.client_id is not None

    async def connect_and_wait(self, timeout: int = 30) -> None:
        """
        連接並等待bind完成
        """
        await self.connect()
        try:
            await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(None, self._bind_event.wait),
                timeout,
            )
        except asyncio.TimeoutError:
            logger.error("Bind timeout")
            await self.close()
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
            await self.close()
            raise TimeoutError("App connect timeout")

    async def connect(self) -> None:
        """
        連接WebSocket
        """
        try:
            self.client = await ws_connect(self.clienturl)
            logger.debug("WebSocket connected")
            self._listen_task = asyncio.create_task(self._listen())
        except Exception as e:
            logger.error(f"WebSocket connection error: {e}")
            await self.close()
            raise ConnectionError("WebSocket connection error")

    async def _listen(self):
        try:
            async for message in self.client:
                await self._handle_message(message)
        except websockets.ConnectionClosed:
            logger.debug("WebSocket connection closed")
            self._stop_heartbeat()
        except Exception as e:
            logger.error(f"WebSocket error: {e}")

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

    async def _update_connects(self, message: WSMessage):
        if message.targetID:
            self.target_id = message.targetID
            await self.set_strength(Channel.A, StrengthType.SPECIFIC, self.strength.A)
            await self.set_strength(Channel.B, StrengthType.SPECIFIC, self.strength.B)
            self._app_connect_event.set()

    async def _heartbeat(self):
        try:
            while not self._closing:
                await self._send_message(
                    {"type": "heartbeat", "clientId": self.client_id, "message": "200"}, update=False
                )

                if self.target_id is None:
                    self._disconnect_count += 1
                    if self._disconnect_count >= self.disconnect_time:
                        logger.error("Disconnected from app")
                        await self.close()
                        break
                else:
                    self._disconnect_count = 0

                await asyncio.sleep(self.interval)

        except websockets.ConnectionClosed:
            logger.info("WebSocket connection closed")
        except Exception as e:
            logger.error(f"Heartbeat error: {e}")

    def _start_heartbeat(self):
        """啟動心跳檢測"""
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
        self._heartbeat_task = asyncio.create_task(self._heartbeat())

    async def _handle_message(self, data: str):
        try:
            message = json.loads(data)
            WSmsg = WSMessage(message)
            if WSmsg.type == WStype.BIND:
                self.client_id = WSmsg.clientID
                self._start_heartbeat()
                await self._update_connects(WSmsg)
                self._bind_event.set()

            elif WSmsg.type == WStype.MSG:
                if WSmsg.msg.startswith("feedback"):
                    button = WSmsg.feedback()
                    await self._dispatch_button(button)
                elif WSmsg.msg.startswith("strength"):
                    self.strength.set_strength(WSmsg.strength())
                    await self._dispatch_strength(WSmsg.strength())
                else:
                    logger.warning(f"Unknown message type: {WSmsg.msg}")

            logger.debug(f"Received message: {message}")
        except Exception as e:
            logger.warning(f"Error: {e}")
            logger.debug(f"Received raw message: {data}")

    async def _send_message(self, message: dict, update: bool = True) -> None:
        try:
            if self.client and self.client.state == websockets.client.State.OPEN:
                if update:
                    message.update({"clientId": self.client_id, "targetId": self.target_id})
                await self.client.send(json.dumps(message))
                logger.debug(f"Sent message: {json.dumps(message)}")
            else:
                logger.error("WebSocket not connected")
        except websockets.ConnectionClosed:
            logger.error("WebSocket connection closed")
        except Exception as e:
            logger.error(f"Error on sending message: {e}")

    async def close(self):
        """
        斷開連結
        """
        self._closing = True
        try:
            for task in [self._heartbeat_task, self._listen_task]:
                if task and not task.done():
                    task.cancel()
            if self.client:
                await self.client.close()
                logger.debug("WebSocket closed")
        except Exception as e:
            logger.error(f"Error on closing WebSocket: {e}")
        finally:
            self.client = None
            self._heartbeat_task = None
            self._listen_task = None
            self._closing = False
            self._app_connect_event.clear()
            self._bind_event.clear()

    @staticmethod
    def _wave2hex(data):
        return ["".join(format(num, "02X") for num in sum(item, [])) for item in data]

    async def send_wave_message(self, wave, time: int = 10, channel: Channel = Channel.BOTH):
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
                await self._send_message(message)
        else:
            message = _create_wave_message(channel, wave, time)
            await self._send_message(message)

    async def clear_wave(self, channel: Channel):
        if channel == Channel.A:
            await self._send_message(
                {
                    "type": "msg",
                    "message": "clear-1",
                }
            )
        elif channel == Channel.B:
            await self._send_message(
                {
                    "type": "msg",
                    "message": "clear-2",
                }
            )
        elif channel == Channel.BOTH:
            await self._send_message(
                {
                    "type": "msg",
                    "message": "clear-1",
                }
            )
            await self._send_message(
                {
                    "type": "msg",
                    "message": "clear-2",
                }
            )
        else:
            logger.error(f"Invalid channel: {channel}")

    async def clear_all_wave(self):
        # type : msg 固定不变
        # message: clear-1 -> 清除A通道波形队列; clear-2 -> 清除B通道波形队列
        await self._send_message(
            {
                "type": "msg",
                "message": "clear-1",
            }
        )
        await self._send_message(
            {
                "type": "msg",
                "message": "clear-2",
            }
        )
        logger.debug("Cleared all waves")
        return True

    async def set_strength_value(self, channel: Channel, strength: int) -> None:
        """
        设置通道强度
        """
        await self.set_strength(channel, StrengthType.SPECIFIC, strength)

    async def add_strength_value(self, channel: Channel, strength: int) -> None:
        """
        增加通道強度
        """
        if channel == Channel.BOTH:
            await self.add_strength_value(Channel.A, strength)
            await self.add_strength_value(Channel.B, strength)
            return
        now_strength = self.strength.A if channel == Channel.A else self.strength.B
        await self.set_strength(channel, StrengthType.SPECIFIC, now_strength + strength)

    async def decrease_strength_value(self, channel: Channel, strength: int) -> None:
        """
        減少通道強度
        """
        if channel == Channel.BOTH:
            await self.decrease_strength_value(Channel.A, strength)
            await self.decrease_strength_value(Channel.B, strength)
            return
        now_strength = self.strength.A if channel == Channel.A else self.strength.B
        await self.set_strength(channel, StrengthType.SPECIFIC, now_strength - strength)

    async def reset_strength_value(self, channel: Channel) -> None:
        """
        通道強度重置為0
        """
        await self.set_strength(channel, StrengthType.ZERO, 0)

    async def set_strength(self, channel: Channel, type_id: StrengthType, strength: int) -> None:
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
                await self._send_message(
                    {
                        "type": type_id,
                        "channel": Channel.A,
                        "strength": strength,
                        "message": MessageType.SET_CHANNEL,
                    }
                )
                await self._send_message(
                    {
                        "type": type_id,
                        "channel": Channel.B,
                        "strength": strength,
                        "message": MessageType.SET_CHANNEL,
                    }
                )
            else:
                await self._send_message(
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
                await self._send_message(
                    {
                        "type": type_id,
                        "message": f"strength-{Channel.A}+{StrengthMode.SPECIFIC}+{self.strength.A}",
                    }
                )
                await self._send_message(
                    {
                        "type": type_id,
                        "message": f"strength-{Channel.B}+{StrengthMode.SPECIFIC}+{self.strength.B}",
                    }
                )
            else:
                if channel == Channel.A:
                    self.strength.A = strength
                    await self._send_message(
                        {
                            "type": type_id,
                            "message": f"strength-{channel}+{StrengthMode.SPECIFIC}+{self.strength.A}",
                        }
                    )
                elif channel == Channel.B:
                    self.strength.B = strength
                    await self._send_message(
                        {
                            "type": type_id,
                            "message": f"strength-{channel}+{StrengthMode.SPECIFIC}+{self.strength.B}",
                        }
                    )

        else:
            logger.error(f"Invalid type id: {type_id}")
            return

    def get_strength_value(self, channel: Channel) -> int:
        """
        獲取通道強度
        """
        match channel:
            case Channel.A:
                return self.strength.A
            case Channel.B:
                return self.strength.B
            case Channel.BOTH:
                return min(self.strength.A, self.strength.B)

    def get_max_strength_value(self, channel: Channel) -> int:
        """
        獲取通道最大強度
        """
        match channel:
            case Channel.A:
                return self.strength.MAX_A
            case Channel.B:
                return self.strength.MAX_B
            case Channel.BOTH:
                return min(self.strength.MAX_A, self.strength.MAX_B)


if __name__ == "__main__":

    async def main():
        client = dglabv3()

        try:
            await client.connect_and_wait()
            qr_code = client.generate_qrcode_text()
            print(qr_code)

        except Exception as e:
            logger.error(f"Error: {e}")
            await client.close()

    asyncio.run(main())

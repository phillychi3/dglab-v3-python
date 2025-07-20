import asyncio
import io
import json
import logging
from threading import Event
from typing import Optional

import qrcode
import websockets
from websockets.asyncio.client import connect as ws_connect

from dglabv3.dtype import Button, Channel, ChannelStrength, MessageType, Strength, StrengthMode, StrengthType
from dglabv3.event import EventEmitter
from dglabv3.music_to_wave import convert_audio_to_v3_protocol
from dglabv3.wsmessage import WSMessage, WStype

logging.basicConfig(level=logging.INFO)
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
        self.bot = None

    async def _dispatch_button(self, button: Button) -> None:
        """
        按鈕事件

        :param button: 按鈕物件
        """
        self.emit("button", button)
        if self.bot:
            await self.bot.dispatch("dglab_button", button)

    async def _dispatch_strength(self, strength: Strength) -> None:
        """
        強度事件

        :param strength: 強度物件
        """
        logger.debug(f"Dispatch strength: {strength}")
        self.emit("strength", strength)
        if self.bot:
            await self.bot.dispatch("dglab_strength", strength)

    def set_bot(self, bot):
        """
        設置Discord Bot

        :param bot: Discord Bot
        """
        self.bot = bot

    def is_connected(self) -> bool:
        """
        檢查是否已連接到WebSocket伺服器

        :return: 連接狀態
        """
        return self.client is not None

    def is_linked_to_app(self) -> bool:
        """
        檢查是否已連接到App

        :return: App連接狀態
        """
        return self.client_id is not None

    async def connect_and_wait(self, timeout: int = 30) -> None:
        """
        連接WebSocket並等待綁定完成

        :param timeout: 超時時間(秒)
        :raises TimeoutError: 當綁定超時
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
        等待App連接

        :param timeout: 超時時間(秒)
        :raises TimeoutError: 當App連接超時
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
        連接到WebSocket伺服器

        :raises ConnectionError: 當連接失敗時
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
        """
        監聽WebSocket訊息
        """
        try:
            if self.client is None:
                logger.error("WebSocket client is None")
                return
            async for message in self.client:
                await self._handle_message(message)
        except websockets.ConnectionClosed:
            logger.debug("WebSocket connection closed")
        except Exception as e:
            logger.error(f"WebSocket error: {e}")
            raise ConnectionError("WebSocket error")

    def generate_qrcode(self) -> Optional[io.BytesIO]:
        """
        生成QR code圖片

        :return: QR code圖片的BytesIO物件，如果client_id為空則返回None
        """
        if self.client_id is None:
            logger.error("Client ID is empty, please connect to the server first")
            return
        qr = qrcode.QRCode()
        qr.add_data(self.clientqrurl + self.client_id)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        saveimg = io.BytesIO()
        img.save(saveimg)
        saveimg.seek(0)
        return saveimg

    def generate_qrcode_text(self) -> Optional[str]:
        """
        生成QR code文字

        :return: ASCII格式的QR code文字，如果client_id為空則返回None
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
        """
        更新連接狀態並同步強度設定

        :param message: WebSocket訊息物件
        """
        if message.targetID:
            self.target_id = message.targetID
            await self.set_strength(Channel.A, StrengthType.SPECIFIC, self.strength.A)
            await self.set_strength(Channel.B, StrengthType.SPECIFIC, self.strength.B)
            self._app_connect_event.set()

    async def _heartbeat(self):
        """
        心跳檢測任務，維持連接並檢測App連接狀態
        """
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
            await self.close()
        except Exception as e:
            logger.error(f"Heartbeat error: {e}")

    def _start_heartbeat(self):
        """
        啟動心跳檢測任務
        """
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
        self._heartbeat_task = asyncio.create_task(self._heartbeat())

    async def _handle_message(self, data: websockets.Data):
        """
        處理接收到的WebSocket訊息

        :param data: WebSocket訊息資料
        """
        try:
            message = json.loads(data)
            WSmsg = WSMessage(message)
            if WSmsg.type == WStype.BIND:
                self.client_id = WSmsg.clientID
                self._start_heartbeat()
                await self._update_connects(WSmsg)
                self._bind_event.set()

            elif WSmsg.type == WStype.MSG:
                if WSmsg.msg is not None:
                    if WSmsg.msg.startswith("feedback"):
                        button = WSmsg.feedback()
                        await self._dispatch_button(button)
                    elif WSmsg.msg.startswith("strength"):
                        self.strength.set_strength(WSmsg.strength())
                        await self._dispatch_strength(WSmsg.strength())
                    else:
                        logger.warning(f"Unknown message type: {WSmsg.msg}")
                else:
                    logger.warning("Received message with None content")

            logger.debug(f"Received message: {message}")
        except Exception as e:
            logger.warning(f"Error: {e}")
            logger.debug(f"Received raw message: {data}")

    async def _send_message(self, message: dict, update: bool = True) -> None:
        """
        發送WebSocket訊息

        :param message: 要發送的訊息字典
        :param update: 是否自動添加clientId和targetId
        """
        try:
            if self.client:
                if update:
                    message.update({"clientId": self.client_id, "targetId": self.target_id})
                await self.client.send(json.dumps(message))
                logger.debug(f"Sent message: {json.dumps(message)}")
            else:
                logger.error("WebSocket not connected")
        except websockets.ConnectionClosed:
            logger.debug("WebSocket connection closed")
        except Exception as e:
            logger.error(f"Error on sending message: {e}")

    async def close(self):
        """
        關閉WebSocket連接並清理資源
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
        """
        將波形資料轉換為16進制字串

        :param data: 波形資料
        :return: 16進制字串列表
        """
        return ["".join(format(num, "02X") for num in sum(item, [])) for item in data]

    async def music_2_wave(self, mp3_file_path: str, channel: Channel = Channel.BOTH):
        """
        將音樂檔案轉換為波形並發送

        :param mp3_file_path: 音樂檔案路徑
        :param channel: 目標通道，預設為雙通道

        Example:

        >>> await client.music_2_wave("music.mp3", Channel.A)
        """
        data = convert_audio_to_v3_protocol(mp3_file_path)
        await self.send_wave_message(data, channel=channel)

    async def send_wave_message(self, wave: list[list[list[int]]], time: int = 10, channel: Channel = Channel.BOTH):
        """
        發送波形\n

        :param wave: 波形數據
        :param time: 波形持續時間(秒)
        :param channel: Channel.A or Channel.B or Channel.BOTH

        Example:

        >>> await client.send_wave_message(PULSES["呼吸"], 30, Channel.A)

        """
        channel_str = ""
        if channel == Channel.A:
            channel_str = "A"
        elif channel == Channel.B:
            channel_str = "B"
        elif channel == Channel.BOTH:
            channel_str = "BOTH"

        def _create_wave_message(ch_str: str, wave: list[list[list[int]]], time: int) -> dict:
            if len(wave) <= 4:  # 避免波型過小
                wave = wave * 2
            return {
                "type": MessageType.CLIENT_MSG,
                "channel": ch_str,
                "message": f"{ch_str}:{json.dumps(self._wave2hex(wave))}",
                "time": time,
            }

        # type : clientMsg 固定不变
        # message : A通道波形数据(16进制HEX数组json,具体见上面的协议说明)
        # message2 : B通道波形数据(16进制HEX数组json,具体见上面的协议说明)
        # time1 : A通道波形数据持续发送时长
        # time2 : B通道波形数据持续发送时长
        if channel_str == "BOTH":
            for ch in ["A", "B"]:
                message = _create_wave_message(ch, wave, time)
                await self._send_message(message)
        else:
            message = _create_wave_message(channel_str, wave, time)
            await self._send_message(message)

    async def clear_wave(self, channel: Channel):
        """
        清除指定通道的波形

        :param channel: 要清除的通道

        Example:

        >>> await client.clear_wave(Channel.A)
        """
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
        """
        清除所有通道的波形

        :return: 操作成功返回True

        Example:

        >>> await client.clear_all_wave()
        """
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
        設定通道強度值

        :param channel: 目標通道
        :param strength: 強度值[0-200]

        Example:

        >>> await client.set_strength_value(Channel.A, 50)
        """
        await self.set_strength(channel, StrengthType.SPECIFIC, strength)

    async def add_strength_value(self, channel: Channel, strength: int) -> None:
        """
        增加通道強度

        :param channel: 目標通道
        :param strength: 要增加的強度值

        Example:

        >>> await client.add_strength_value(Channel.A, 10)
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

        :param channel: 目標通道
        :param strength: 要減少的強度值

        Example:

        >>> await client.decrease_strength_value(Channel.A, 5)
        """
        if channel == Channel.BOTH:
            await self.decrease_strength_value(Channel.A, strength)
            await self.decrease_strength_value(Channel.B, strength)
            return
        now_strength = self.strength.A if channel == Channel.A else self.strength.B
        await self.set_strength(channel, StrengthType.SPECIFIC, now_strength - strength)

    async def reset_strength_value(self, channel: Channel) -> None:
        """
        重置通道強度為0

        :param channel: 目標通道

        Example:

        >>> await client.reset_strength_value(Channel.A)
        """
        await self.set_strength(channel, StrengthType.ZERO, 0)

    async def set_strength(self, channel: Channel, type_id: StrengthType, strength: int) -> None:
        """
        設定通道強度

        :param channel: 目標通道
        :param type_id: 強度類型
        :param strength: 強度值[0-200]

        Example:

        >>> await client.set_strength(Channel.A, StrengthType.SPECIFIC, 80)
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

        :param channel: 目標通道
        :return: 強度值

        Example:

        >>> strength = client.get_strength_value(Channel.A)
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

        :param channel: 目標通道
        :return: 最大強度值

        Example:

        >>> max_strength = client.get_max_strength_value(Channel.A)
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

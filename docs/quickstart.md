# 快速開始

## V3

```python
import asyncio
from dglabv3 import dglabv3, Channel, Pulse

client = dglabv3()


async def run():
    try:
        await client.connect()
        print(client.generate_qrcode_text())
        await client.wait_for_app_connect()

        await client.set_strength_value(Channel.A, 10)
        await client.send_wave_message(Pulse().breath, 30, Channel.A)
        await asyncio.sleep(30)
    finally:
        await client.close()


asyncio.run(run())
```

## V4

只需注入 `V4Protocol`，其餘用法相同：

```python
from dglabv3 import dglabv3, V4Protocol

client = dglabv3(V4Protocol())
```

`client.send_wave_message()`、`client.set_strength_value()` 等方法作用在**預設設備** (`client.device`)，優先選擇已藍牙連接的郊狼。

## QR code

| 方法                     | 回傳                           |
| ------------------------ | ------------------------------ |
| `generate_qrcode()`      | PNG 圖片的 `BytesIO`           |
| `generate_qrcode_text()` | 可在終端機顯示的 ASCII QR code |
| `get_qrcode_url()`       | QR code 內容的網址             |

## 波形

內建波形可透過 `Pulse()` 或 `PULSES` 取得：

```python
from dglabv3 import Pulse, PULSES, ALL_PULSES

Pulse().breath
Pulse().random_pulse()
```

也可以直接傳入16進制字串列表，每個字串為一幀 (100ms)：

```python
await client.send_wave_message(["0A0A0A0A64646464", "0A0A0A0A00000000"], 10, Channel.A)
```

# DGLAB V3 webhook

僅提供客戶端\
並無伺服端功能

> [!Warning]
> 絕讚開發中，測試尚未編寫完全

## 安裝

```bash
pip install --upgrade dglabv3
```

## 簡單範例

```python
import asyncio
from dglabv3 import dglabv3
from dglabv3 import Channel, StrengthType, Pulse


client = dglabv3()


async def run():
    try:
        await client.connect_and_wait(timeout=30)
        print(client.generate_qrcode_text())
        await client.wait_for_app_connect(timeout=60)
        client.set_strength_value(Channel.A, 20)
        await asyncio.sleep(1)
        client.send_wave_message(Pulse().breath, 30, Channel.A)

    except Exception as e:
        print(f"An error occurred: {e}")
        exit(1)


if __name__ == "__main__":
    asyncio.run(run())

```

> [!Note]
> 如果發現無法設置到自己想要的強度，請檢察目前最高強度在哪裡，預設是40秒+1最大上限，可以手動拉高
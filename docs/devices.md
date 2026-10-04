# 設備

V4 的 App 會上報設備列表，`DeviceRegistry` 依設備類型建立對應類別：

| 類別     | 設備類型                    | 設備               | 功能                               |
| -------- | --------------------------- | ------------------ | ---------------------------------- |
| `Coyote` | `COYOTE_020` / `COYOTE_030` | 郊狼 V2 / V3       | 強度、波形、通道狀態、舒適強度限制 |
| `Ovc`    | `OVC_1`                     | 負鼠振動控制器     | 強度、波形、配件插入狀態、模式     |
| `Bmtr`   | `BMTR_1`                    | 靈貓邊緣控制傳感器 | 只讀：壓力、邊控狀態               |
| `Device` | 其他                        | 未知設備           | 原始 `props` / `slot_state`        |

## 取得設備

```python
client.device                  # 預設輸出設備
client.devices                 # 所有 App 的所有設備
client.get_device(Ovc)         # 第一個負鼠
client.get_devices(Coyote)     # 所有郊狼
client.get_device(slot_id="...")
```

## 操作設備

`Coyote` 與 `Ovc` 繼承自 `OutputDevice`，channel 可使用 `Channel.A` / `Channel.B` / `Channel.BOTH`：

```python
ovc = client.get_device(Ovc)
await ovc.add_strength(Channel.A, 5)
await ovc.set_strength(Channel.BOTH, 20)
await ovc.send_wave(Pulse().wave, 10, Channel.BOTH)
await ovc.clear()
```

## 讀取狀態

```python
coyote = client.get_device(Coyote)
coyote.has_device                    # 是否已藍牙連接
coyote.power                         # 電量
coyote.get_strength(Channel.A)
coyote.get_max_strength(Channel.A)
coyote.is_muted(Channel.A)
coyote.channel_status(Channel.A)     # CoyoteChannelStatus

bmtr = client.get_device(Bmtr)
bmtr.pressure
bmtr.edge_state                      # EdgeState
```

App 上報的原始資料保存在 `device.props` 與 `device.slot_state`。

:::{note}
`has_device` 為 `False` 或通道 `is_muted` 為 `True` 時，指令可能不會有實際輸出。
:::

## 自訂設備類別

```python
from dglabv3 import dglabv3, V4Protocol, DeviceRegistry, DeviceType, Coyote, Channel


class MyCoyote(Coyote):
    async def punish(self):
        await self.set_temp_strength(Channel.BOTH, 30, 3000)


registry = DeviceRegistry.default().register(DeviceType.COYOTE_030, MyCoyote)
client = dglabv3(V4Protocol(), registry=registry)
```

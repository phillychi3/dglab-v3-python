# 協議


```python
client = dglabv3()                  # 預設 V3Protocol()
client = dglabv3(V4Protocol())
client = dglabv3(V4Protocol(url="wss://my-server/v4"))  # 自架伺服器
```

|                              | V3                           | V4                                           |
| ---------------------------- | ---------------------------- | -------------------------------------------- |
| App                          | 舊版 DG-LAB App              | DG-LAB 4 App                                 |
| 預設伺服器                   | `wss://ws.dungeon-lab.cn/`   | `wss://trex.dungeon-lab.cn/v4`               |
| App 數量                     | 1                            | 多個                                         |
| 設備                         | 單一郊狼 (`slot_id="v3"`)    | 郊狼、負鼠、靈貓                             |
| 指定強度                     | 原生支援                     | 依當前強度計算差值後調整                     |
| 臨時強度 `set_temp_strength` | 不支援 (`NotSupportedError`) | 支援                                         |
| 指令回應                     | 無                           | 等待 App 回應，錯誤時拋出 `AppResponseError` |

## V4 的指令回應

V4 的每個設備操作都是 RPC 請求，App 會在任務**結束**時才回應：

- 強度操作預設會等待回應
- `send_wave` / `send_pulse` / `set_temp_strength` 預設**不等待**，回傳 `Future`；傳入 `wait=True` 可等待播放結束

V4 操作可額外傳入：

| 參數        | 說明                                     |
| ----------- | ---------------------------------------- |
| `wait`      | 是否等待 App 回應                        |
| `priority`  | `Priority.LOW` / `NORMAL` / `HIGH`       |
| `immediate` | 是否替換同設備、同通道、同類型的已有任務 |

這些參數在 V3 下會被忽略。

## 自訂協議

繼承 `Protocol` 並實作抽象方法即可，詳見 {class}`dglabv3.protocols.Protocol`。

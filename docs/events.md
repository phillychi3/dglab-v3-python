# 事件

使用 `@client.event()` 註冊，函式名稱去掉 `on_` 前綴即為事件名稱，同步與非同步函式皆可：

```python
@client.event()
def on_strength(strength):
    print(strength.A, strength.B)


@client.event()
async def on_app_connect(client_id):
    ...
```

| 事件             | 參數                 | 說明                                      |
| ---------------- | -------------------- | ----------------------------------------- |
| `app_connect`    | `client_id`          | App 已連接                                |
| `app_disconnect` | `client_id`          | App 已斷開                                |
| `devices`        | `devices, client_id` | 設備列表變化                              |
| `device`         | `device, client_id`  | 單一設備狀態變化                          |
| `strength`       | `Strength`           | 輸出設備強度變化                          |
| `action`         | `action, client_id`  | App 自定義動作 (V3 為按鈕 1-6，V4 為 0-9) |
| `button`         | `Button`             | App 按鈕 (僅 V3)                          |
| `disconnect`     |                      | 與伺服器斷開                              |

## Discord Bot

透過 `set_bot` 設定後，事件會以 `dglab_` 前綴轉發給 Bot：

```python
client.set_bot(bot)


@bot.event
async def on_dglab_strength(strength):
    ...
```

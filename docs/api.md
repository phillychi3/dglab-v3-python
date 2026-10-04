# API 參考

## 客戶端

```{eval-rst}
.. autoclass:: dglabv3.dglabv3
```

## 協議

```{eval-rst}
.. autoclass:: dglabv3.protocols.Protocol

.. autoclass:: dglabv3.protocols.V3Protocol
   :no-members:

.. autoclass:: dglabv3.protocols.V4Protocol
   :no-members:
```

## 設備

```{eval-rst}
.. autoclass:: dglabv3.devices.Device

.. autoclass:: dglabv3.devices.OutputDevice

.. autoclass:: dglabv3.devices.Coyote

.. autoclass:: dglabv3.devices.CoyoteChannelStatus
   :undoc-members:

.. autoclass:: dglabv3.devices.Ovc

.. autoclass:: dglabv3.devices.OvcMode
   :undoc-members:

.. autoclass:: dglabv3.devices.Bmtr

.. autoclass:: dglabv3.devices.EdgeState
   :undoc-members:

.. autoclass:: dglabv3.devices.App

.. autoclass:: dglabv3.devices.DeviceRegistry
```

## 型別

```{eval-rst}
.. autoclass:: dglabv3.Channel
   :undoc-members:

.. autoclass:: dglabv3.Strength
   :undoc-members:

.. autoclass:: dglabv3.DeviceType
   :undoc-members:

.. autoclass:: dglabv3.Priority
   :undoc-members:

.. autoclass:: dglabv3.StrengthType
   :undoc-members:

.. autoclass:: dglabv3.Button
   :undoc-members:
```

## 波形

```{eval-rst}
.. autoclass:: dglabv3.Pulse
```

- `PULSES`：`dict[str, list]`，波形名稱對應波形資料
- `ALL_PULSES`：`list[str]`，所有內建波形名稱

## 錯誤

```{eval-rst}
.. autoexception:: dglabv3.DGLabError

.. autoexception:: dglabv3.NotSupportedError

.. autoexception:: dglabv3.AppResponseError
```

import asyncio
import json
from urllib.parse import unquote

import pytest

from dglabv3 import (
    AppResponseError,
    Bmtr,
    Button,
    Channel,
    Coyote,
    DeviceRegistry,
    DeviceType,
    EdgeState,
    NotSupportedError,
    Ovc,
    Pulse,
    Strength,
    V3Protocol,
    V4Protocol,
    dglabv3,
)
from dglabv3.devices.base import merge_patch


class FakeWS:
    def __init__(self):
        self.sent: list[dict] = []

    async def send(self, text):
        self.sent.append(json.loads(text))

    async def close(self):
        pass


COYOTE = {
    "slotId": "slot-c",
    "name": "郊狼",
    "type": "COYOTE_030",
    "props": {"intensityA": 5, "intensityB": 0},
    "slotState": {"hasDevice": True, "channelA": {"intensityMax": 80}, "channelB": {"intensityMax": 60}},
}
OVC = {"slotId": "slot-o", "name": "負鼠", "type": "OVC_1", "props": {"intensityA": 0, "channelAStatus": True}}
BMTR = {"slotId": "slot-b", "name": "靈貓", "type": "BMTR_1", "props": {"pressure": 12}, "slotState": {"edge": {"edgeState": 1}}}


async def feed(client: dglabv3, frame: dict) -> None:
    await client.protocol.handle_message(json.dumps(frame))


def app_msg(data: dict) -> dict:
    return {"type": "message", "clientId": "app-1", "data": data}


async def make_v4(registry=None) -> tuple[dglabv3, FakeWS]:
    client = dglabv3(V4Protocol(), registry=registry)
    ws = FakeWS()
    client.protocol.ws = ws
    await feed(client, {"type": "hello", "clientId": "ctrl-1"})
    await feed(client, {"type": "client_attached", "clientId": "app-1"})
    await feed(client, app_msg({"t": "ev", "ev": "devices.snapshot", "devices": [OVC, COYOTE, BMTR]}))
    return client, ws


async def respond(client: dglabv3, ws: FakeWS, result=None, error=None) -> None:
    data = {"t": "resp", "reqId": ws.sent[-1]["data"]["reqId"]}
    data.update({"error": error} if error else {"result": result})
    await feed(client, app_msg(data))


def run(coro):
    asyncio.run(coro)


def test_merge_patch():
    assert merge_patch({"a": {"b": 1, "c": 2}}, {"a": {"c": 3}}) == {"a": {"b": 1, "c": 3}}


def test_default_protocol_is_v3():
    assert isinstance(dglabv3().protocol, V3Protocol)


# ---------------------------------------------------------------------- V4


def test_v4_handshake_and_devices():
    async def main():
        client, _ = await make_v4()
        assert client.target_id == "ctrl-1"
        url = client.get_qrcode_url()
        assert url.startswith("https://dungeon-lab.cn/s/?v=1&action=socket&url=")
        assert unquote(url.split("url=")[1]) == "wss://trex.dungeon-lab.cn/v4?tid=ctrl-1"

        app = await client.wait_for_app_connect(timeout=1)
        assert app.client_id == "app-1"
        assert [type(d) for d in client.devices] == [Ovc, Coyote, Bmtr]
        assert isinstance(client.device, Coyote)  # 預設設備優先郊狼
        assert client.get_device(Ovc).has_accessory(Channel.A)
        bmtr = client.get_device(Bmtr)
        assert bmtr.pressure == 12 and bmtr.edge_state == EdgeState.STIMULATING
        assert client.get_strength_value(Channel.A) == 5
        assert client.get_max_strength_value(Channel.BOTH) == 60
        await client.close()

    run(main())


def test_v4_slots_patch_emits_strength_and_device():
    async def main():
        client, _ = await make_v4()
        strengths, devices = [], []
        client.register_event("strength", strengths.append)
        client.register_event("device", lambda d, cid: devices.append(d))
        await feed(
            client,
            app_msg(
                {
                    "t": "ev",
                    "ev": "slots.patch",
                    "slots": [{"slotId": "slot-c", "props": {"intensityA": 9}}, {"slotId": "slot-b", "props": {"pressure": 30}}],
                }
            ),
        )
        assert strengths == [Strength(A=9, B=0, MAXA=80, MAXB=60, client_id="app-1", slot_id="slot-c")]
        assert [d.slot_id for d in devices] == ["slot-c", "slot-b"]
        assert client.get_device(Bmtr).pressure == 30
        await client.close()

    run(main())


def test_v4_ovc_operation_targets_its_slot():
    async def main():
        client, ws = await make_v4()
        ovc = client.get_device(Ovc)
        task = asyncio.create_task(ovc.add_strength(Channel.B, 3))
        await asyncio.sleep(0)
        frame = ws.sent[-1]
        assert frame["clientId"] == "app-1" and frame["data"]["m"] == "device.op"
        assert frame["data"]["data"] == {"s": "slot-o", "t": 3, "c": 1, "v": 3}
        await respond(client, ws, {"reason": "completed"})
        assert (await task)["reason"] == "completed"
        await client.close()

    run(main())


def test_v4_response_error():
    async def main():
        client, ws = await make_v4()
        task = asyncio.create_task(client.reset_strength_value(Channel.A))
        await asyncio.sleep(0)
        assert ws.sent[-1]["data"]["data"] == {"s": "slot-c", "t": 7, "c": 0, "v": 0}
        await respond(client, ws, error="slot_not_found")
        with pytest.raises(AppResponseError, match="slot_not_found"):
            await task
        await client.close()

    run(main())


def test_v4_set_strength_uses_delta():
    async def main():
        client, ws = await make_v4()
        task = asyncio.create_task(client.set_strength_value(Channel.A, 20))
        await asyncio.sleep(0)
        assert ws.sent[-1]["data"]["data"] == {"s": "slot-c", "t": 3, "c": 0, "v": 15}
        await respond(client, ws, {})
        await task
        with pytest.raises(ValueError):
            await client.set_strength_value(Channel.A, 81)
        await client.close()

    run(main())


def test_v4_send_wave_repeats_frames():
    async def main():
        client, ws = await make_v4()
        wave = [[[10, 10, 10, 10], [0, 0, 0, 0]], [[10, 10, 10, 10], [100, 100, 100, 100]]]
        futures = await client.send_wave_message(wave, 1, Channel.BOTH)
        ops = [f["data"]["data"] for f in ws.sent[-2:]]
        assert [op["c"] for op in ops] == [0, 1]
        assert ops[0]["d"] == 1000
        assert ops[0]["v"] == ["0A0A0A0A00000000", "0A0A0A0A64646464"] * 5
        assert not any(f.done() for f in futures)
        await client.close()
        assert all(f.done() for f in futures)

    run(main())


def test_v4_app_disconnect_rejects_pending():
    async def main():
        client, ws = await make_v4()
        task = asyncio.create_task(client.clear_wave(Channel.A))
        await asyncio.sleep(0)
        assert ws.sent[-1]["data"] == {**ws.sent[-1]["data"], "m": "device.op.clear", "data": {"s": "slot-c", "c": 0}}
        await feed(client, {"type": "client_disconnected", "clientId": "app-1"})
        with pytest.raises(Exception, match="App disconnected"):
            await task
        assert not client.is_linked_to_app()
        await client.close()

    run(main())


def test_registry_injection():
    class MyOvc(Ovc):
        pass

    async def main():
        client, _ = await make_v4(DeviceRegistry.default().register(DeviceType.OVC_1, MyOvc))
        assert isinstance(client.get_device(Ovc), MyOvc)
        await client.close()

    run(main())


# ---------------------------------------------------------------------- V3


async def make_v3() -> tuple[dglabv3, FakeWS]:
    client = dglabv3(V3Protocol())
    ws = FakeWS()
    client.protocol.ws = ws
    await feed(client, {"type": "bind", "clientId": "ctrl-1", "targetId": "", "message": "targetId"})
    await feed(client, {"type": "bind", "clientId": "ctrl-1", "targetId": "app-1", "message": "200"})
    return client, ws


def test_v3_pair_and_qrcode():
    async def main():
        client, _ = await make_v3()
        assert client.get_qrcode_url() == "https://www.dungeon-lab.com/app-download.php#DGLAB-SOCKET#wss://ws.dungeon-lab.cn/ctrl-1"
        app = await client.wait_for_app_connect(timeout=1)
        assert app.client_id == "app-1"
        assert isinstance(client.device, Coyote)
        await client.close()

    run(main())


def test_v3_strength_and_feedback_events():
    async def main():
        client, _ = await make_v3()
        strengths, buttons, actions = [], [], []
        client.register_event("strength", strengths.append)
        client.register_event("button", buttons.append)
        client.register_event("action", lambda a, cid: actions.append(a))
        await feed(client, {"type": "msg", "clientId": "ctrl-1", "targetId": "app-1", "message": "strength-11+7+100+35"})
        await feed(client, {"type": "msg", "clientId": "ctrl-1", "targetId": "app-1", "message": "feedback-3"})
        assert strengths == [Strength(A=11, B=7, MAXA=100, MAXB=35, client_id="app-1", slot_id="v3")]
        assert client.get_max_strength_value(Channel.B) == 35
        assert buttons == [Button.button_3] and actions == [3]
        await client.close()

    run(main())


def test_v3_operations():
    async def main():
        client, ws = await make_v3()
        await client.set_strength_value(Channel.A, 20)
        assert ws.sent[-1] == {"type": 4, "message": "strength-1+2+20", "clientId": "ctrl-1", "targetId": "app-1"}
        await client.decrease_strength_value(Channel.B, 3)
        assert ws.sent[-1]["message"] == "strength-2+0+3"
        await client.send_wave_message(Pulse().breath, 30, Channel.A)
        assert ws.sent[-1]["type"] == "clientMsg" and ws.sent[-1]["time"] == 30
        assert ws.sent[-1]["message"].startswith('A:["0A0A0A0A00000000"')
        await client.clear_wave(Channel.BOTH)
        assert [m["message"] for m in ws.sent[-2:]] == ["clear-1", "clear-2"]
        with pytest.raises(NotSupportedError):
            await client.set_temp_strength(Channel.A, 10, 1000)
        await client.close()

    run(main())

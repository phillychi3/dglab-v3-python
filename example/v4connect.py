import asyncio
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dglabv3 import Bmtr, Channel, Device, Pulse, Strength, V4Protocol, dglabv3

client = dglabv3(V4Protocol())


@client.event()
def on_strength(strength: Strength) -> None:
    print(f"強度: {strength}")


@client.event()
def on_devices(devices: list[Device], client_id: str) -> None:
    print(f"App {client_id} 設備: {devices}")


@client.event()
def on_action(action: int, client_id: str) -> None:
    print(f"App {client_id} 動作: {action}")


async def run():
    try:
        await client.connect_and_wait()
        print(client.generate_qrcode_text())
        print("請使用 DG-LAB 4 App 掃描 QR code")

        await client.wait_for_app_connect(timeout=120)
        await client.reset_strength_value(Channel.BOTH)
        await client.add_strength_value(Channel.A, 10)
        await client.send_wave_message(Pulse().breath, 10, Channel.A)
        await asyncio.sleep(10)
        await client.clear_all_wave()

    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(run())

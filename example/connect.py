import asyncio
from PIL import Image
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dglabv3 import dglabv3
from dglabv3 import Channel, StrengthType, PULSES


client = dglabv3()


async def run():
    try:
        await client.connect_and_wait()
        qrcode = client.generate_qrcode()
        ig = Image.open(qrcode)
        ig.show()
        await client.wait_for_app_connect()
        await client.set_strength(Channel.A, StrengthType.SPECIFIC, 1)
        await asyncio.sleep(1)
        await client.send_wave_message(PULSES["呼吸"], 30, Channel.A)
        await asyncio.sleep(10)

    except Exception as e:
        print(f"An error occurred: {e}")
        exit(1)
    finally:
        await client.close()

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(run())
    finally:
        loop.close()

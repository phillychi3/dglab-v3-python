import random

import discord
from discord import app_commands
from discord.ext import commands

from dglabv3 import ALL_PULSES, PULSES, Channel, Pulse, Strength, dglabv3


class dglab:
    def __init__(self):
        self.dungeon = {}

    def add_dg(self, userid, dungeon):
        self.dungeon[userid] = dungeon

    def get_dg(self, userid):
        try:
            return self.dungeon[userid]
        except KeyError:
            return None

    def del_dg(self, userid):
        del self.dungeon[userid]


_dg = dglab()


class dglab_input_class(discord.ui.Modal, title="手動輸入數值"):
    hint = discord.ui.TextInput(label="提示", placeholder="波型將使用目前選擇波型(此框輸入無效)", required=False)
    strength = discord.ui.TextInput(label="強度", placeholder="請輸入強度(1~200)", min_length=1, max_length=200)
    sec = discord.ui.TextInput(label="秒數", placeholder="請輸入秒數(1~20)", min_length=1, max_length=20)

    def __init__(self, user_id):
        super().__init__()
        self.user_id = user_id

    async def on_submit(self, interaction: discord.Interaction, /) -> None:
        dg: dglab_conteol_class = _dg.get_dg(self.user_id)
        if not dg:
            await interaction.response.send_message(embed=discord.Embed(title="找不到控制器"), ephemeral=True)
            return
        try:
            power = int(self.strength.value)
            sec = int(self.sec.value)
        except ValueError:
            await interaction.response.send_message(embed=discord.Embed(title="輸入錯誤"), ephemeral=True)
            return
        if power > dg.client.get_max_strength_value(dg.channel):
            dg.logadd(f"設定強度 {power} 超過最大值，已調整為最大值")
            power = dg.client.get_max_strength_value(dg.channel)
        if sec > 20:
            sec = 20
        await dg.client.set_strength_value(dg.channel, power)
        await dg.client.send_wave_message(dg.now_wave, sec, dg.channel)
        dg.logadd(f"{interaction.user.name} 手動輸入了 {power}%  {sec}秒")
        await interaction.response.edit_message(embed=dg.embed)

    async def on_error(self, interaction: discord.Interaction, error: Exception, /) -> None:
        await interaction.response.send_message(embed=discord.Embed(title="輸入失敗"), ephemeral=True)


class dglab_conteol_class:
    def __init__(self, embed: discord.Embed) -> None:
        self.embed = embed
        self.strength = Strength(0, 0, 0, 0)
        self.now_wave = Pulse().breath
        self.wave_name = "breath"
        self.channel = Channel.BOTH
        self.client = dglabv3()
        self.log = []

    def get_channel_name(self):
        if self.channel == Channel.A:
            return "A通道"
        elif self.channel == Channel.B:
            return "B通道"
        else:
            return "全部"

    def edit_embed(self):
        self.embed.description = f"A通道強度: `{self.client.get_strength_value(Channel.A)}%`\nB通道強度: `{self.client.get_strength_value(Channel.B)}%`\nA通道最大強度: `{self.client.get_max_strength_value(Channel.A)}%`\nB通道最大強度: `{self.client.get_max_strength_value(Channel.B)}%`\n目前通道: `{self.get_channel_name()}`\n目前波形: `{self.wave_name}`"

    def logadd(self, log):
        self.edit_embed()
        self.log.append(log)
        if len(self.log) > 7:
            self.log.pop(0)
        formatted_log = "\n".join(self.log)
        self.embed.set_field_at(0, name="log", value=f"```{formatted_log}```")


class chose_wave_select(discord.ui.Select):
    def __init__(self, user_id):
        super().__init__(placeholder="請選擇波形", options=[], custom_id="wave_select")
        self.user_id = user_id
        for pulse in ALL_PULSES:
            self.add_option(label=pulse, value=pulse)

    async def callback(self, interaction: discord.Interaction):
        dg: dglab_conteol_class = _dg.get_dg(self.user_id)
        dg.now_wave = PULSES[interaction.data["values"][0]]
        dg.wave_name = interaction.data["values"][0]
        dg.edit_embed()
        await interaction.response.edit_message(embed=dg.embed)


class control_view(discord.ui.View):
    def __init__(self, user_id):
        super().__init__(timeout=None)
        self.add_item(chose_wave_select(user_id))
        self.user_id = user_id
        self.a_button = discord.ui.Button(label="A通道", style=discord.ButtonStyle.primary)
        self.b_button = discord.ui.Button(label="B通道", style=discord.ButtonStyle.primary)
        self.all_button = discord.ui.Button(label="全通道", style=discord.ButtonStyle.primary)
        self.a_button.callback = self.a_channel
        self.b_button.callback = self.b_channel
        self.all_button.callback = self.both_channel
        self.add_item(self.a_button)
        self.add_item(self.b_button)
        self.add_item(self.all_button)

    async def a_channel(self, interaction: discord.Interaction, button: discord.ui.Button):
        dg: dglab_conteol_class = _dg.get_dg(self.user_id)
        dg.channel = Channel.A
        dg.edit_embed()
        button.style = discord.ButtonStyle.success
        self.b_button.style = discord.ButtonStyle.primary
        self.all_button.style = discord.ButtonStyle.primary
        await interaction.response.edit_message(embed=dg.embed)

    async def b_channel(self, interaction: discord.Interaction, button: discord.ui.Button):
        dg: dglab_conteol_class = _dg.get_dg(self.user_id)
        dg.channel = Channel.B
        dg.edit_embed()
        button.style = discord.ButtonStyle.success
        self.a_button.style = discord.ButtonStyle.primary
        self.all_button.style = discord.ButtonStyle.primary
        await interaction.response.edit_message(embed=dg.embed)

    async def both_channel(self, interaction: discord.Interaction, button: discord.ui.Button):
        dg: dglab_conteol_class = _dg.get_dg(self.user_id)
        dg.channel = Channel.BOTH
        dg.edit_embed()
        button.style = discord.ButtonStyle.success
        self.a_button.style = discord.ButtonStyle.primary
        self.b_button.style = discord.ButtonStyle.primary
        await interaction.response.edit_message(embed=dg.embed)

    @discord.ui.button(label="挑逗", style=discord.ButtonStyle.green)
    async def start_cake_level2(self, interaction: discord.Interaction, button: discord.ui.Button):
        dg: dglab_conteol_class = _dg.get_dg(self.user_id)
        power = random.randint(10, 30)
        if power > dg.client.get_max_strength_value(dg.channel):
            dg.logadd(f"設定強度 {power} 超過最大值，已調整為最大值")
            power = dg.client.get_max_strength_value(dg.channel)
        sec = random.randint(2, 15)
        await dg.client.set_strength_value(dg.channel, power)
        await dg.client.send_wave_message(dg.now_wave, sec, dg.channel)
        dg.logadd(f"{interaction.user.name} 開啟了挑逗 {power}%  {sec}秒")
        await interaction.response.edit_message(embed=dg.embed)

    @discord.ui.button(label="來點感覺", style=discord.ButtonStyle.green)
    async def start_cake_level3(self, interaction: discord.Interaction, button: discord.ui.Button):
        dg: dglab_conteol_class = _dg.get_dg(self.user_id)
        power = random.randint(30, 60)
        if power > dg.client.get_max_strength_value(dg.channel):
            dg.logadd(f"設定強度 {power} 超過最大值，已調整為最大值")
            power = dg.client.get_max_strength_value(dg.channel)
        sec = random.randint(2, 15)
        await dg.client.set_strength_value(dg.channel, power)
        await dg.client.send_wave_message(dg.now_wave, sec, dg.channel)
        dg.logadd(f"{interaction.user.name} 開啟了快感 {power}%  {sec}秒")
        await interaction.response.edit_message(embed=dg.embed)

    @discord.ui.button(label="電他", style=discord.ButtonStyle.green)
    async def start_cake_level4(self, interaction: discord.Interaction, button: discord.ui.Button):
        dg: dglab_conteol_class = _dg.get_dg(self.user_id)
        power = random.randint(60, 100)
        if power > dg.client.get_max_strength_value(dg.channel):
            dg.logadd(f"設定強度 {power} 超過最大值，已調整為最大值")
            power = dg.client.get_max_strength_value(dg.channel)
        sec = random.randint(2, 15)
        await dg.client.set_strength_value(dg.channel, power)
        await dg.client.send_wave_message(dg.now_wave, sec, dg.channel)
        dg.logadd(f"{interaction.user.name} 開啟了懲罰 {power}%  {sec}秒")
        await interaction.response.edit_message(embed=dg.embed)

    @discord.ui.button(label="手動輸入", style=discord.ButtonStyle.green)
    async def manual_input(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(dglab_input_class(self.user_id))

    @discord.ui.button(label="重新整理", style=discord.ButtonStyle.blurple)
    async def refresh(self, interaction: discord.Interaction, button: discord.ui.Button):
        dg: dglab_conteol_class = _dg.get_dg(self.user_id)
        dg.edit_embed()
        await interaction.response.edit_message(embed=dg.embed)

    @discord.ui.button(label="斷開連接", style=discord.ButtonStyle.red, custom_id="disconnect")
    async def disconnect(self, interaction: discord.Interaction, button: discord.ui.Button):
        dg: dglab_conteol_class = _dg.get_dg(self.user_id)
        await dg.client.close()
        _dg.del_dg(self.user_id)
        await interaction.response.edit_message(embed=dg.embed, view=None)


class dglabv3class(commands.Cog):
    @app_commands.command(description="你的蛋糕控制器 (請勿隨意使用)")
    async def start_a_cakev3(self, interaction: discord.Interaction):
        embed = discord.Embed(title="連結APP", description="掃描qrcode")
        embed.add_field(name="log", value="nothing")
        dg_class = dglab_conteol_class(embed)
        _dg.add_dg(interaction.user.id, dg_class)
        try:
            await dg_class.client.connect_and_wait()
            qrcode = dg_class.client.generate_qrcode()
            await interaction.response.send_message(embed=embed)
            wms = await interaction.followup.send(file=discord.File(qrcode, filename="qrcode.png"), ephemeral=True)
            await dg_class.client.wait_for_app_connect()
            await wms.delete()
            embed.title = "已連接"
            embed.description = f"A通道強度: `{dg_class.client.get_strength_value(Channel.A)}%`\nB通道強度: `{dg_class.client.get_strength_value(Channel.B)}%`\nA通道最大強度: `{dg_class.client.get_max_strength_value(Channel.A)}%`\nB通道最大強度: `{dg_class.client.get_max_strength_value(Channel.B)}%`"
            await interaction.edit_original_response(embed=embed, view=control_view(interaction.user.id))
        except Exception as e:
            await dg_class.client.close()
            _dg.del_dg(interaction.user.id)
            await interaction.followup.send(embed=discord.Embed(title=str(e)), ephemeral=True)


async def setup(bot):
    await bot.add_cog(dglabv3class(bot))

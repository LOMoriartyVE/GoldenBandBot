import asyncio
import os
import sys
import threading
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
PREFIX = os.getenv("COMMAND_PREFIX", "!")
ADMIN_USER_ID = os.getenv("ADMIN_USER_ID")
ENABLE_LOCAL_HOTKEY = os.getenv("ENABLE_LOCAL_HOTKEY", "false").lower() in ("true", "1", "yes")
HOTKEY_COMBO = os.getenv("HOTKEY", "ctrl+alt+p").lower()

if not TOKEN or TOKEN == "your_bot_token_here":
    print("=" * 60)
    print("ERROR: DISCORD_TOKEN is missing in your .env file!")
    print("Please create a .env file with: DISCORD_TOKEN=your_token_here")
    print("=" * 60)
    sys.exit(1)

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True
intents.guilds = True

bot = commands.Bot(command_prefix=PREFIX, intents=intents)


async def ensure_bot_in_channel(channel: discord.VoiceChannel):
    """Ensures the bot is connected to the specified voice channel."""
    guild = channel.guild
    voice_client = guild.voice_client

    if voice_client is None:
        try:
            await channel.connect()
        except Exception as e:
            print(f"[Voice] Could not connect to {channel.name}: {e}")
    elif voice_client.channel != channel:
        try:
            await voice_client.move_to(channel)
        except Exception as e:
            print(f"[Voice] Could not move to {channel.name}: {e}")


async def execute_mute_channel(
    channel: discord.VoiceChannel,
    target_mute: bool,
    exclude_user_id: Optional[int] = None,
) -> tuple[int, int]:
    """
    Mutes or unmutes non-bot members in the given voice channel.
    If exclude_user_id is None, mutes/unmutes EVERYONE including the caller.
    Returns: (successful_count, failed_count)
    """
    success = 0
    failed = 0

    for member in channel.members:
        if member.bot:
            continue
        if exclude_user_id and member.id == exclude_user_id:
            continue

        try:
            # Only update if current state differs
            if member.voice and member.voice.mute != target_mute:
                await member.edit(mute=target_mute)
                success += 1
        except discord.Forbidden:
            failed += 1
        except Exception as e:
            print(f"[Mute Error] Could not update {member.display_name}: {e}")
            failed += 1

    return success, failed


class VoiceControlView(discord.ui.View):
    """Interactive Discord buttons for admins to click and control voice channels."""

    def __init__(self):
        super().__init__(timeout=None)

    async def _handle_action(
        self,
        interaction: discord.Interaction,
        target_mute: bool,
        action_name: str,
    ):
        member = interaction.user
        if not isinstance(member, discord.Member):
            await interaction.response.send_message(
                "❌ This command must be used within a server.", ephemeral=True
            )
            return

        has_perm = (
            member.guild_permissions.administrator
            or member.guild_permissions.mute_members
        )
        if not has_perm:
            await interaction.response.send_message(
                "❌ You need the **Mute Members** or **Administrator** permission to use this.",
                ephemeral=True,
            )
            return

        if not member.voice or not member.voice.channel:
            await interaction.response.send_message(
                "⚠️ You must be connected to a voice channel first!",
                ephemeral=True,
            )
            return

        channel = member.voice.channel
        await interaction.response.defer(ephemeral=True)

        # Mutes/unmutes EVERYONE in the channel (including the admin)
        success, failed = await execute_mute_channel(
            channel=channel,
            target_mute=target_mute,
            exclude_user_id=None,
        )

        status_text = f"✅ **{action_name}** executed in **{channel.name}**!\n"
        status_text += f"• Modified: **{success}** members\n"
        if failed > 0:
            status_text += (
                f"⚠️ **{failed}** members could not be modified.\n"
                f"*(Note: Discord forbids bots from muting Server Owners or users with a higher role than the bot. Drag Charlotte's role to the top in Server Settings -> Roles!)*"
            )

        await interaction.followup.send(status_text, ephemeral=True)

    @discord.ui.button(label="Mute All", style=discord.ButtonStyle.danger, emoji="🔇", custom_id="btn_mute_all")
    async def mute_all_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._handle_action(interaction, target_mute=True, action_name="Mute All")

    @discord.ui.button(label="Unmute All", style=discord.ButtonStyle.success, emoji="🔊", custom_id="btn_unmute_all")
    async def unmute_all_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._handle_action(interaction, target_mute=False, action_name="Unmute All")

    @discord.ui.button(label="Join / Move Bot", style=discord.ButtonStyle.secondary, emoji="🎧", custom_id="btn_join_bot")
    async def join_bot_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        member = interaction.user
        if not isinstance(member, discord.Member) or not member.voice or not member.voice.channel:
            await interaction.response.send_message("⚠️ You must be in a voice channel first!", ephemeral=True)
            return

        channel = member.voice.channel
        await ensure_bot_in_channel(channel)
        await interaction.response.send_message(f"🎧 Charlotte joined **{channel.name}**!", ephemeral=True)

    @discord.ui.button(label="Leave Voice", style=discord.ButtonStyle.secondary, emoji="👋", custom_id="btn_leave_bot")
    async def leave_bot_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        if guild and guild.voice_client:
            await guild.voice_client.disconnect()
            await interaction.response.send_message("👋 Charlotte left the voice channel.", ephemeral=True)
        else:
            await interaction.response.send_message("⚠️ Charlotte is not in any voice channel.", ephemeral=True)


@bot.event
async def on_ready():
    print("=" * 60)
    print(f"Logged in as: {bot.user.name}#{bot.user.discriminator} (ID: {bot.user.id})")
    print(f"Connected to {len(bot.guilds)} server(s):")
    for guild in bot.guilds:
        print(f" - {guild.name} (ID: {guild.id})")
    
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} application (slash) commands.")
    except Exception as e:
        print(f"Failed to sync slash commands: {e}")
    
    print("=" * 60)
    print("Charlotte is online and ready!")
    if ENABLE_LOCAL_HOTKEY:
        print(f"Local Hotkey [{HOTKEY_COMBO.upper()}] is active.")
    print("=" * 60)


# ==========================================
# Slash Commands
# ==========================================

@bot.tree.command(name="join", description="Charlotte joins your current voice channel.")
@app_commands.checks.has_permissions(mute_members=True)
async def slash_join(interaction: discord.Interaction):
    member = interaction.user
    if not isinstance(member, discord.Member) or not member.voice or not member.voice.channel:
        await interaction.response.send_message("⚠️ You must be connected to a voice channel first!", ephemeral=True)
        return

    channel = member.voice.channel
    await ensure_bot_in_channel(channel)
    await interaction.response.send_message(f"🎧 Joined **{channel.name}**!")


@bot.tree.command(name="leave", description="Charlotte leaves the voice channel.")
@app_commands.checks.has_permissions(mute_members=True)
async def slash_leave(interaction: discord.Interaction):
    if interaction.guild and interaction.guild.voice_client:
        await interaction.guild.voice_client.disconnect()
        await interaction.response.send_message("👋 Left the voice channel.")
    else:
        await interaction.response.send_message("⚠️ Charlotte is not connected to a voice channel.", ephemeral=True)


@bot.tree.command(name="voicepanel", description="Displays interactive buttons to Mute/Unmute/Join voice.")
@app_commands.checks.has_permissions(mute_members=True)
async def slash_voicepanel(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🎙️ Charlotte Voice Moderation Panel",
        description=(
            "Click the buttons below to control the voice channel you are currently in.\n\n"
            "• 🔇 **Mute All**: Server-mutes everyone except you.\n"
            "• 🔊 **Unmute All**: Unmutes everyone in the channel.\n"
            "• 🎧 **Join / Move Bot**: Brings Charlotte into your voice room.\n"
            "• 👋 **Leave Voice**: Disconnects Charlotte."
        ),
        color=discord.Color.blue(),
    )
    embed.set_footer(text="Requires 'Mute Members' or 'Administrator' permission.")
    await interaction.response.send_message(embed=embed, view=VoiceControlView())


@bot.tree.command(name="muteall", description="Server-mutes everyone in your current voice channel.")
@app_commands.checks.has_permissions(mute_members=True)
async def slash_muteall(interaction: discord.Interaction):
    member = interaction.user
    if not isinstance(member, discord.Member) or not member.voice or not member.voice.channel:
        await interaction.response.send_message("⚠️ You must be connected to a voice channel first!", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=False)
    channel = member.voice.channel
    success, failed = await execute_mute_channel(channel, target_mute=True, exclude_user_id=None)

    msg = f"🔇 **Muted everyone in {channel.name}** ({success} updated)."
    if failed:
        msg += f"\n*(⚠️ {failed} members could not be muted. Make sure Charlotte's role is above them!)*"
    await interaction.followup.send(msg)


@bot.tree.command(name="unmuteall", description="Unmutes everyone in your current voice channel.")
@app_commands.checks.has_permissions(mute_members=True)
async def slash_unmuteall(interaction: discord.Interaction):
    member = interaction.user
    if not isinstance(member, discord.Member) or not member.voice or not member.voice.channel:
        await interaction.response.send_message("⚠️ You must be connected to a voice channel first!", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=False)
    channel = member.voice.channel
    success, failed = await execute_mute_channel(channel, target_mute=False)

    msg = f"🔊 **Unmuted everyone in {channel.name}** ({success} updated)."
    if failed:
        msg += f" ({failed} members could not be unmuted)."
    await interaction.followup.send(msg)


# ==========================================
# Traditional Prefix Commands (!join, !leave, etc.)
# ==========================================

@bot.command(name="join")
@commands.has_permissions(mute_members=True)
async def cmd_join(ctx: commands.Context):
    if not ctx.author.voice or not ctx.author.voice.channel:
        await ctx.send("⚠️ You must be in a voice channel first!")
        return
    channel = ctx.author.voice.channel
    await ensure_bot_in_channel(channel)
    await ctx.send(f"🎧 Joined **{channel.name}**!")


@bot.command(name="leave")
@commands.has_permissions(mute_members=True)
async def cmd_leave(ctx: commands.Context):
    if ctx.guild and ctx.guild.voice_client:
        await ctx.guild.voice_client.disconnect()
        await ctx.send("👋 Left the voice channel.")
    else:
        await ctx.send("⚠️ Charlotte is not connected to a voice channel.")


@bot.command(name="voicepanel")
@commands.has_permissions(mute_members=True)
async def cmd_voicepanel(ctx: commands.Context):
    embed = discord.Embed(
        title="🎙️ Charlotte Voice Moderation Panel",
        description=(
            "Click the buttons below to control the voice channel you are currently in.\n\n"
            "• 🔇 **Mute All**: Server-mutes everyone except you.\n"
            "• 🔊 **Unmute All**: Unmutes everyone in the channel.\n"
            "• 🎧 **Join / Move Bot**: Brings Charlotte into your voice room.\n"
            "• 👋 **Leave Voice**: Disconnects Charlotte."
        ),
        color=discord.Color.blue(),
    )
    embed.set_footer(text="Requires 'Mute Members' or 'Administrator' permission.")
    await ctx.send(embed=embed, view=VoiceControlView())


@bot.command(name="muteall")
@commands.has_permissions(mute_members=True)
async def cmd_muteall(ctx: commands.Context):
    if not ctx.author.voice or not ctx.author.voice.channel:
        await ctx.send("⚠️ You must be in a voice channel to use this command!")
        return

    channel = ctx.author.voice.channel
    success, failed = await execute_mute_channel(channel, target_mute=True, exclude_user_id=None)
    msg = f"🔇 Muted everyone in **{channel.name}** ({success} members)."
    if failed:
        msg += f"\n*(⚠️ {failed} could not be modified due to role permissions)*"
    await ctx.send(msg)


@bot.command(name="unmuteall")
@commands.has_permissions(mute_members=True)
async def cmd_unmuteall(ctx: commands.Context):
    if not ctx.author.voice or not ctx.author.voice.channel:
        await ctx.send("⚠️ You must be in a voice channel to use this command!")
        return

    channel = ctx.author.voice.channel
    success, failed = await execute_mute_channel(channel, target_mute=False)
    msg = f"🔊 Unmuted everyone in **{channel.name}** ({success} members)."
    if failed:
        msg += f" *(Note: {failed} could not be modified)*"
    await ctx.send(msg)


# ==========================================
# Local Hotkey Listener (Ctrl + Alt + P)
# ==========================================

_hotkey_muted_state = False

def start_local_hotkey_listener(loop: asyncio.AbstractEventLoop):
    """
    Listens for the configured shortcut (default Ctrl+Alt+P) locally on Windows.
    Toggles mute/unmute for everyone in the voice channel of ADMIN_USER_ID,
    and connects the bot to the channel if not already joined.
    """
    try:
        import keyboard
    except ImportError:
        print("[Hotkey] 'keyboard' package is not installed. Install with: pip install keyboard")
        return

    if not ADMIN_USER_ID:
        print("[Hotkey] Notice: ADMIN_USER_ID is not set in .env. Hotkey won't know which user's channel to target.")
        return

    try:
        admin_id = int(ADMIN_USER_ID)
    except ValueError:
        print("[Hotkey] Invalid ADMIN_USER_ID format. It must be a numeric Discord ID.")
        return

    async def hotkey_trigger():
        global _hotkey_muted_state
        _hotkey_muted_state = not _hotkey_muted_state
        target_mute = _hotkey_muted_state
        action_word = "Muting" if target_mute else "Unmuting"

        found_channel = None
        for guild in bot.guilds:
            member = guild.get_member(admin_id)
            if member and member.voice and member.voice.channel:
                found_channel = member.voice.channel
                break

        if not found_channel:
            print(f"[Hotkey {HOTKEY_COMBO.upper()}] Admin ({admin_id}) is not currently in any voice channel.")
            return

        # Ensure bot joins the voice channel too
        await ensure_bot_in_channel(found_channel)

        print(f"[Hotkey {HOTKEY_COMBO.upper()}] {action_word} everyone in '{found_channel.name}'...")
        success, failed = await execute_mute_channel(
            channel=found_channel,
            target_mute=target_mute,
            exclude_user_id=None,  # Mutes everyone including the admin
        )
        print(f"[Hotkey {HOTKEY_COMBO.upper()}] Result: {success} modified, {failed} failed.")

    def on_hotkey_pressed():
        asyncio.run_coroutine_threadsafe(hotkey_trigger(), loop)

    keyboard.add_hotkey(HOTKEY_COMBO, on_hotkey_pressed)
    print(f"[Hotkey] Successfully registered global Windows shortcut: {HOTKEY_COMBO.upper()}")


# ==========================================
# Main Startup
# ==========================================

if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    if ENABLE_LOCAL_HOTKEY:
        hotkey_thread = threading.Thread(
            target=start_local_hotkey_listener, args=(loop,), daemon=True
        )
        hotkey_thread.start()

    try:
        loop.run_until_complete(bot.start(TOKEN))
    except KeyboardInterrupt:
        print("Shutting down bot...")
        loop.run_until_complete(bot.close())
    finally:
        loop.close()



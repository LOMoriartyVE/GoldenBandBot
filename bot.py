import asyncio
import json
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

# ==========================================
# Force Mute Storage & State
# ==========================================

FORCE_MUTED_FILE = "force_muted.json"

def load_force_muted() -> set[int]:
    """Loads force-muted user IDs from file."""
    if os.path.exists(FORCE_MUTED_FILE):
        try:
            with open(FORCE_MUTED_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return set(int(uid) for uid in data)
        except Exception as e:
            print(f"[ForceMute] Could not load {FORCE_MUTED_FILE}: {e}")
            return set()
    return set()

def save_force_muted(users: set[int]):
    """Saves force-muted user IDs to file."""
    try:
        with open(FORCE_MUTED_FILE, "w", encoding="utf-8") as f:
            json.dump(list(users), f, indent=2)
    except Exception as e:
        print(f"[ForceMute] Could not save {FORCE_MUTED_FILE}: {e}")

force_muted_users: set[int] = load_force_muted()


@bot.event
async def on_voice_state_update(member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
    """
    Enforces force-mute: If a force-muted user joins a channel or tries to unmute,
    Charlotte immediately re-mutes them.
    """
    if member.id in force_muted_users and after.channel is not None:
        if not after.mute:
            try:
                await member.edit(mute=True)
            except discord.Forbidden:
                pass
            except Exception as e:
                print(f"[ForceMute Enforce Error] Could not re-mute {member.display_name}: {e}")


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
    Force-muted users are NEVER unmuted by channel-wide unmuteall commands.
    Returns: (successful_count, failed_count)
    """
    success = 0
    failed = 0

    for member in channel.members:
        if member.bot:
            continue
        if exclude_user_id and member.id == exclude_user_id:
            continue
        # Protect force-muted users from being unmuted during unmuteall
        if not target_mute and member.id in force_muted_users:
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


@bot.tree.command(name="mute", description="Server-mutes a specific member in voice.")
@app_commands.describe(member="The member you want to mute in voice")
@app_commands.checks.has_permissions(mute_members=True)
async def slash_mute(interaction: discord.Interaction, member: discord.Member):
    if not member.voice or not member.voice.channel:
        await interaction.response.send_message(
            f"⚠️ **{member.display_name}** is not in any voice channel.", ephemeral=True
        )
        return

    if member.voice.mute:
        await interaction.response.send_message(
            f"ℹ️ **{member.display_name}** is already server-muted.", ephemeral=True
        )
        return

    try:
        await member.edit(mute=True)
        await interaction.response.send_message(
            f"🔇 **{member.mention}** has been server-muted in **{member.voice.channel.name}**."
        )
    except discord.Forbidden:
        await interaction.response.send_message(
            f"❌ Could not mute **{member.display_name}**! "
            f"Make sure Charlotte's role is placed **above** their role in Server Settings → Roles.",
            ephemeral=True,
        )
    except Exception as e:
        await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)


@bot.tree.command(name="unmute", description="Server-unmutes a specific member in voice.")
@app_commands.describe(member="The member you want to unmute in voice")
@app_commands.checks.has_permissions(mute_members=True)
async def slash_unmute(interaction: discord.Interaction, member: discord.Member):
    if member.id in force_muted_users:
        await interaction.response.send_message(
            f"⚠️ **{member.display_name}** is **Force-Muted**!\n"
            f"Use `/forceunmute` or `!forceunmute` to release them first.",
            ephemeral=True,
        )
        return

    if not member.voice or not member.voice.channel:
        await interaction.response.send_message(
            f"⚠️ **{member.display_name}** is not in any voice channel.", ephemeral=True
        )
        return

    if not member.voice.mute:
        await interaction.response.send_message(
            f"ℹ️ **{member.display_name}** is not server-muted.", ephemeral=True
        )
        return

    try:
        await member.edit(mute=False)
        await interaction.response.send_message(
            f"🔊 **{member.mention}** has been server-unmuted in **{member.voice.channel.name}**."
        )
    except discord.Forbidden:
        await interaction.response.send_message(
            f"❌ Could not unmute **{member.display_name}**! "
            f"Check Charlotte's role hierarchy and permissions.",
            ephemeral=True,
        )
    except Exception as e:
        await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)


@bot.tree.command(name="forcemute", description="Force-mutes a member. They cannot be unmuted by unmuteall.")
@app_commands.describe(member="The member to lock in muted state")
@app_commands.checks.has_permissions(mute_members=True)
async def slash_forcemute(interaction: discord.Interaction, member: discord.Member):
    if member.bot:
        await interaction.response.send_message("❌ Bots cannot be force-muted.", ephemeral=True)
        return

    force_muted_users.add(member.id)
    save_force_muted(force_muted_users)

    if member.voice and member.voice.channel:
        try:
            await member.edit(mute=True)
        except discord.Forbidden:
            await interaction.response.send_message(
                f"⚠️ Added {member.mention} to Force-Mute list, but Charlotte's role is too low to mute them right now. "
                f"(Make sure Charlotte's role is above them in Server Roles!).",
                ephemeral=True,
            )
            return

    await interaction.response.send_message(
        f"🔨 **{member.mention}** has been **Force-Muted**!\n"
        f"They will stay muted even if `/unmuteall` or `!unmuteall` is used.\n"
        f"Use `/forceunmute` or `!forceunmute` to release them."
    )


@bot.tree.command(name="forceunmute", description="Removes the force-mute lock from a member.")
@app_commands.describe(member="The member to release from force-mute")
@app_commands.checks.has_permissions(mute_members=True)
async def slash_forceunmute(interaction: discord.Interaction, member: discord.Member):
    if member.id not in force_muted_users:
        await interaction.response.send_message(
            f"ℹ️ **{member.display_name}** is not in the Force-Mute list.", ephemeral=True
        )
        return

    force_muted_users.discard(member.id)
    save_force_muted(force_muted_users)

    if member.voice and member.voice.channel and member.voice.mute:
        try:
            await member.edit(mute=False)
        except Exception:
            pass

    await interaction.response.send_message(
        f"🔓 **{member.mention}** has been released from Force-Mute and can speak again."
    )


@bot.tree.command(name="forcemuted", description="Shows list of all currently force-muted users.")
@app_commands.checks.has_permissions(mute_members=True)
async def slash_forcemuted(interaction: discord.Interaction):
    if not force_muted_users:
        await interaction.response.send_message("ℹ️ No users are currently force-muted.", ephemeral=True)
        return

    lines = []
    for uid in list(force_muted_users):
        user = interaction.guild.get_member(uid) if interaction.guild else None
        if user:
            lines.append(f"• {user.mention} (`{user.display_name}` - ID: `{uid}`)")
        else:
            lines.append(f"• User ID: `{uid}`")

    embed = discord.Embed(
        title="🔨 Force-Muted Users",
        description="\n".join(lines),
        color=discord.Color.dark_red(),
    )
    embed.set_footer(text="These users will NOT be unmuted by unmuteall.")
    await interaction.response.send_message(embed=embed, ephemeral=True)


# Right-click User -> Apps -> Mute / Unmute / Force Mute / Force Unmute
@bot.tree.context_menu(name="Mute in Voice")
@app_commands.checks.has_permissions(mute_members=True)
async def context_mute(interaction: discord.Interaction, member: discord.Member):
    if not member.voice or not member.voice.channel:
        await interaction.response.send_message(
            f"⚠️ **{member.display_name}** is not in a voice channel.", ephemeral=True
        )
        return

    try:
        await member.edit(mute=True)
        await interaction.response.send_message(
            f"🔇 **{member.mention}** has been server-muted.", ephemeral=True
        )
    except discord.Forbidden:
        await interaction.response.send_message(
            f"❌ Cannot mute **{member.display_name}**. Ensure Charlotte's role is higher.", ephemeral=True
        )


@bot.tree.context_menu(name="Unmute in Voice")
@app_commands.checks.has_permissions(mute_members=True)
async def context_unmute(interaction: discord.Interaction, member: discord.Member):
    if member.id in force_muted_users:
        await interaction.response.send_message(
            f"⚠️ **{member.display_name}** is **Force-Muted**! Use Force Unmute to release them.",
            ephemeral=True,
        )
        return

    if not member.voice or not member.voice.channel:
        await interaction.response.send_message(
            f"⚠️ **{member.display_name}** is not in a voice channel.", ephemeral=True
        )
        return

    try:
        await member.edit(mute=False)
        await interaction.response.send_message(
            f"🔊 **{member.mention}** has been server-unmuted.", ephemeral=True
        )
    except discord.Forbidden:
        await interaction.response.send_message(
            f"❌ Cannot unmute **{member.display_name}**. Check role permissions.", ephemeral=True
        )


@bot.tree.context_menu(name="Force Mute")
@app_commands.checks.has_permissions(mute_members=True)
async def context_forcemute(interaction: discord.Interaction, member: discord.Member):
    if member.bot:
        await interaction.response.send_message("❌ Bots cannot be force-muted.", ephemeral=True)
        return
    force_muted_users.add(member.id)
    save_force_muted(force_muted_users)
    if member.voice and member.voice.channel:
        try:
            await member.edit(mute=True)
        except discord.Forbidden:
            pass
    await interaction.response.send_message(
        f"🔨 **{member.mention}** is now **Force-Muted** (immune to unmuteall).", ephemeral=True
    )


@bot.tree.context_menu(name="Force Unmute")
@app_commands.checks.has_permissions(mute_members=True)
async def context_forceunmute(interaction: discord.Interaction, member: discord.Member):
    force_muted_users.discard(member.id)
    save_force_muted(force_muted_users)
    if member.voice and member.voice.channel and member.voice.mute:
        try:
            await member.edit(mute=False)
        except Exception:
            pass
    await interaction.response.send_message(
        f"🔓 **{member.mention}** is no longer Force-Muted.", ephemeral=True
    )


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


@bot.command(name="mute")
@commands.has_permissions(mute_members=True)
async def cmd_mute(ctx: commands.Context, member: discord.Member):
    if not member.voice or not member.voice.channel:
        await ctx.send(f"⚠️ **{member.display_name}** is not in any voice channel.")
        return

    if member.voice.mute:
        await ctx.send(f"ℹ️ **{member.display_name}** is already server-muted.")
        return

    try:
        await member.edit(mute=True)
        await ctx.send(f"🔇 **{member.mention}** has been server-muted.")
    except discord.Forbidden:
        await ctx.send(
            f"❌ Could not mute **{member.display_name}**. "
            f"Make sure Charlotte's role is placed **above** their role in Server Settings → Roles!"
        )
    except Exception as e:
        await ctx.send(f"❌ Error: {e}")


@bot.command(name="unmute")
@commands.has_permissions(mute_members=True)
async def cmd_unmute(ctx: commands.Context, member: discord.Member):
    if member.id in force_muted_users:
        await ctx.send(
            f"⚠️ **{member.display_name}** is **Force-Muted**!\n"
            f"Use `!forceunmute {member.mention}` to release them first."
        )
        return

    if not member.voice or not member.voice.channel:
        await ctx.send(f"⚠️ **{member.display_name}** is not in any voice channel.")
        return

    if not member.voice.mute:
        await ctx.send(f"ℹ️ **{member.display_name}** is not server-muted.")
        return

    try:
        await member.edit(mute=False)
        await ctx.send(f"🔊 **{member.mention}** has been server-unmuted.")
    except discord.Forbidden:
        await ctx.send(
            f"❌ Could not unmute **{member.display_name}**. "
            f"Check Charlotte's role permissions."
        )
    except Exception as e:
        await ctx.send(f"❌ Error: {e}")


@bot.command(name="forcemute")
@commands.has_permissions(mute_members=True)
async def cmd_forcemute(ctx: commands.Context, member: discord.Member):
    if member.bot:
        await ctx.send("❌ Bots cannot be force-muted.")
        return

    force_muted_users.add(member.id)
    save_force_muted(force_muted_users)

    if member.voice and member.voice.channel:
        try:
            await member.edit(mute=True)
        except discord.Forbidden:
            await ctx.send(
                f"⚠️ Added {member.mention} to Force-Mute list, but Charlotte's role is too low to mute them right now. "
                f"(Make sure Charlotte's role is above them in Server Roles!)."
            )
            return

    await ctx.send(
        f"🔨 **{member.mention}** has been **Force-Muted**!\n"
        f"They will stay muted even if `!unmuteall` or `/unmuteall` is used.\n"
        f"Use `!forceunmute {member.mention}` to release them."
    )


@bot.command(name="forceunmute")
@commands.has_permissions(mute_members=True)
async def cmd_forceunmute(ctx: commands.Context, member: discord.Member):
    if member.id not in force_muted_users:
        await ctx.send(f"ℹ️ **{member.display_name}** is not in the Force-Mute list.")
        return

    force_muted_users.discard(member.id)
    save_force_muted(force_muted_users)

    if member.voice and member.voice.channel and member.voice.mute:
        try:
            await member.edit(mute=False)
        except Exception:
            pass

    await ctx.send(f"🔓 **{member.mention}** has been released from Force-Mute and can speak again.")


@bot.command(name="forcemuted")
@commands.has_permissions(mute_members=True)
async def cmd_forcemuted(ctx: commands.Context):
    if not force_muted_users:
        await ctx.send("ℹ️ No users are currently force-muted.")
        return

    lines = []
    for uid in list(force_muted_users):
        user = ctx.guild.get_member(uid) if ctx.guild else None
        if user:
            lines.append(f"• {user.mention} (`{user.display_name}` - ID: `{uid}`)")
        else:
            lines.append(f"• User ID: `{uid}`")

    embed = discord.Embed(
        title="🔨 Force-Muted Users",
        description="\n".join(lines),
        color=discord.Color.dark_red(),
    )
    embed.set_footer(text="These users will NOT be unmuted by unmuteall.")
    await ctx.send(embed=embed)


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



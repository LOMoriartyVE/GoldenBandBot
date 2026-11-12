# 🎙️ Charlotte - Discord Voice Moderation Bot

**Charlotte** is a Discord moderation bot designed for server administrators to quickly bulk-mute and bulk-unmute voice channels using **interactive buttons**, **slash commands**, or an optional **local hotkey (`Ctrl + M`)**.

---

## 📋 Legal Documents
- [Terms of Service](TERMS_OF_SERVICE.md)
- [Privacy Policy](PRIVACY_POLICY.md)

*(Once pushed to GitHub, use the direct raw/blob links in the Discord Developer Portal under General Information).*

---

## ✨ Features

1. **🔘 Clickable Admin Panel (`/voicepanel` or `!voicepanel`)**:
   - Spawns interactive buttons (🔴 **Mute All** & 🟢 **Unmute All**) directly in your text channel.
   - Any server admin can simply click to mute or unmute everyone in their current voice channel.
   - The admin executing the command remains unmuted.

2. **⚡ Slash Commands & Text Commands**:
   - `/muteall` or `!muteall`: Server-mutes everyone in your voice channel.
   - `/unmuteall` or `!unmuteall`: Unmutes everyone in your voice channel.
   - `/voicepanel` or `!voicepanel`: Displays the clickable buttons.

3. **⌨️ Local Windows Hotkey (`Ctrl + M`)**:
   - Optional feature: when running the bot locally on your PC, pressing `Ctrl + M` anywhere on your computer instantly toggles mute/unmute for everyone in your voice channel!

---

## ⚙️ Installation & Setup

### 1. Install Requirements
Open PowerShell or Command Prompt in this folder and run:
```powershell
pip install -r requirements.txt
```

### 2. Configure `.env`
Create a `.env` file in this directory:
```env
DISCORD_TOKEN=your_bot_token_here
COMMAND_PREFIX=!
ADMIN_USER_ID=your_discord_user_id
ENABLE_LOCAL_HOTKEY=false
```

- **`DISCORD_TOKEN`**: Found in [Discord Developer Portal](https://discord.com/developers/applications) → Your App → **Bot** → **Reset Token**.
- **`ADMIN_USER_ID`** *(optional, only if using Ctrl+M)*: In Discord, enable Developer Mode (*Settings → Advanced → Developer Mode*), right-click your profile, and select **Copy User ID**.
- **`ENABLE_LOCAL_HOTKEY`**: Set to `true` if you want the `Ctrl + M` shortcut while running the bot locally.

---

## 🔒 Important Discord Server Role Setup

For Charlotte to be able to mute members:
1. In your Discord server: Go to **Server Settings** → **Roles**.
2. Find the **Charlotte** role.
3. **Drag Charlotte's role ABOVE the roles of the members** you want to mute. (Discord prevents bots from modifying users who have higher roles than the bot).
4. Ensure Charlotte has the **Mute Members** and **View Channel** permissions.

---

## 🚀 Running the Bot

```powershell
python bot.py
```

---

## 🐙 Push to GitHub

1. Initialize git and commit:
```powershell
git init
git add .
git commit -m "Initial commit of Charlotte Discord Bot"
```

2. Link to your GitHub repository and push:
```powershell
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO_NAME.git
git push -u origin main
```


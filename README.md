# Discord ↔ Telegram Sync Bot

> ⚠️ **Warning:** This project is still under development.  
> Some bugs may occur, especially with complex attachments such as large images, certain document formats, or high-volume media forwarding. Use with caution in production environments.

> ℹ️ **Important:** This project’s documentation is written in Brazilian Portuguese (pt-BR).  
> While the codebase is in English, explanations and setup instructions are currently provided in Portuguese.

---

A robust, bi-directional synchronization bot for bridging messages between Discord and Telegram channels.

## Overview

This project enables seamless communication between a Discord text channel and a Telegram group or supergroup. It mirrors messages—including media, replies, and deletions—between platforms using the respective APIs and webhooks.

The solution is ideal for community managers, moderators, and developers maintaining cross-platform communication with minimal overhead.

---

## Features

- Two-way synchronization between Discord and Telegram
- Support for text, images, videos, documents, stickers, and voice messages
- Reply mapping across both platforms
- Real-time deletion tracking and propagation
- User attribution with Telegram profile pictures on Discord via webhooks
- Graceful handling of message types and API failures

---

## Requirements

- Python 3.9 or newer
- Telegram bot token ([via BotFather](https://core.telegram.org/bots#botfather))
- Discord bot token and webhook URL
- Channel and group IDs for both platforms

### Python Dependencies

A full list of required packages is available in `requirements.txt`. To install:

```bash
pip install -r requirements.txt
```

---

## Setup Instructions

1. **Clone the repository:**

   ```bash
   git clone https://github.com/yourusername/discord-telegram-sync.git
   cd discord-telegram-sync
   ```

2. **Edit configuration:**

   Inside the main script, replace the placeholders with your own credentials:

   ```python
   DISCORD_TOKEN = "your-discord-bot-token"
   TELEGRAM_TOKEN = "your-telegram-bot-token"
   WEBHOOK_URL = "https://discord.com/api/webhooks/..."
   DISCORD_CHANNEL_ID = 123456789012345678
   TELEGRAM_CHAT_ID = -123456789
   ```

   > Note: Telegram group IDs typically start with a negative sign (`-`).

3. **Run the bot:**

   ```bash
   python discord_telegram_sync.py
   ```

   The bot will connect to Discord and start polling Telegram for messages.

---

## Deployment Notes

- The current version uses long polling for Telegram.
- Discord messages are captured through event listeners and relayed via webhook.
- The code is structured to be extensible for future enhancements such as:
  - Database logging
  - Admin command interface
  - Advanced media parsing

---

## Limitations

- Does not support Discord threads or Telegram channels
- Some media formats may behave inconsistently across platforms
- Webhook-based replies on Discord have inherent limitations

---

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for more details.

---

## Contributions

Feel free to fork this repository and adapt it to your needs.  
Pull requests are welcome, especially for bug fixes, performance improvements, or new features.  
For any questions, issues, or suggestions, please open an issue on GitHub.

---

**Maintained by [Your Name or Organization].**

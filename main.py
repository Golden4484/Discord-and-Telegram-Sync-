import discord
from discord.ext import commands
import asyncio
import aiohttp
import json
import os
import tempfile
from datetime import datetime
import logging
from typing import Dict, Optional, Tuple
import re

# Logging configuration
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TelegramBot:
    """
    A class to handle Telegram Bot API operations.
    Provides methods to send messages, photos, videos, documents and handle deletions.
    """
    def __init__(self, token: str):
        self.token = token
        self.api_url = f"https://api.telegram.org/bot{token}"
        self.session = None

    async def init_session(self):
        """Initialize aiohttp session for making HTTP requests to Telegram API"""
        if not self.session:
            self.session = aiohttp.ClientSession()

    async def close_session(self):
        """Close the aiohttp session to free up resources"""
        if self.session:
            await self.session.close()

    async def send_message(self, chat_id: int, text: str, reply_to_message_id: Optional[int] = None):
        """
        Send a text message to a Telegram chat.
        
        Args:
            chat_id: The ID of the chat to send the message to
            text: The message text to send
            reply_to_message_id: Optional ID of message to reply to
        
        Returns:
            JSON response from Telegram API
        """
        await self.init_session()
        data = {
            'chat_id': chat_id,
            'text': text,
            'parse_mode': 'HTML'
        }
        if reply_to_message_id:
            data['reply_to_message_id'] = reply_to_message_id

        async with self.session.post(f"{self.api_url}/sendMessage", data=data) as response:
            return await response.json()

    async def send_photo(self, chat_id: int, photo_url: str, caption: str = "", reply_to_message_id: Optional[int] = None):
        """
        Send a photo to a Telegram chat.
        
        Args:
            chat_id: The ID of the chat to send the photo to
            photo_url: URL of the photo to send
            caption: Optional caption for the photo
            reply_to_message_id: Optional ID of message to reply to
        
        Returns:
            JSON response from Telegram API
        """
        await self.init_session()
        data = {
            'chat_id': chat_id,
            'photo': photo_url,
            'caption': caption,
            'parse_mode': 'HTML'
        }
        if reply_to_message_id:
            data['reply_to_message_id'] = reply_to_message_id

        async with self.session.post(f"{self.api_url}/sendPhoto", data=data) as response:
            return await response.json()

    async def send_video(self, chat_id: int, video_url: str, caption: str = "", reply_to_message_id: Optional[int] = None):
        """
        Send a video to a Telegram chat.
        
        Args:
            chat_id: The ID of the chat to send the video to
            video_url: URL of the video to send
            caption: Optional caption for the video
            reply_to_message_id: Optional ID of message to reply to
        
        Returns:
            JSON response from Telegram API
        """
        await self.init_session()
        data = {
            'chat_id': chat_id,
            'video': video_url,
            'caption': caption,
            'parse_mode': 'HTML'
        }
        if reply_to_message_id:
            data['reply_to_message_id'] = reply_to_message_id

        async with self.session.post(f"{self.api_url}/sendVideo", data=data) as response:
            return await response.json()

    async def send_document(self, chat_id: int, document_url: str, caption: str = "", reply_to_message_id: Optional[int] = None):
        """
        Send a document to a Telegram chat.
        
        Args:
            chat_id: The ID of the chat to send the document to
            document_url: URL of the document to send
            caption: Optional caption for the document
            reply_to_message_id: Optional ID of message to reply to
        
        Returns:
            JSON response from Telegram API
        """
        await self.init_session()
        data = {
            'chat_id': chat_id,
            'document': document_url,
            'caption': caption,
            'parse_mode': 'HTML'
        }
        if reply_to_message_id:
            data['reply_to_message_id'] = reply_to_message_id

        async with self.session.post(f"{self.api_url}/sendDocument", data=data) as response:
            return await response.json()

    async def delete_message(self, chat_id: int, message_id: int):
        """
        Delete a message from a Telegram chat.
        
        Args:
            chat_id: The ID of the chat containing the message
            message_id: The ID of the message to delete
        
        Returns:
            JSON response from Telegram API
        """
        await self.init_session()
        data = {
            'chat_id': chat_id,
            'message_id': message_id
        }
        async with self.session.post(f"{self.api_url}/deleteMessage", data=data) as response:
            return await response.json()

    async def get_updates(self, offset: int = 0):
        """
        Get updates from Telegram using long polling.
        
        Args:
            offset: Offset for getting updates (used to acknowledge processed updates)
        
        Returns:
            JSON response containing updates from Telegram API
        """
        await self.init_session()
        params = {'offset': offset, 'timeout': 30}
        async with self.session.get(f"{self.api_url}/getUpdates", params=params) as response:
            return await response.json()

class DiscordTelegramSync:
    """
    Main class that synchronizes messages between Discord and Telegram.
    Handles bidirectional message forwarding, replies, deletions, and media files.
    """
    def __init__(self, discord_token: str, telegram_token: str, webhook_url: str, 
                 discord_channel_id: int, telegram_chat_id: int):
        # Configuration settings
        self.discord_token = discord_token
        self.telegram_token = telegram_token
        self.webhook_url = webhook_url
        self.discord_channel_id = discord_channel_id
        self.telegram_chat_id = telegram_chat_id

        # Initialize bots
        intents = discord.Intents.default()
        intents.message_content = True  # Required to read message content
        self.discord_bot = commands.Bot(command_prefix='!', intents=intents)
        self.telegram_bot = TelegramBot(telegram_token)

        # Bidirectional message mapping for handling replies and deletions
        # Maps Discord message IDs to Telegram message info (msg_id, username, user_id)
        self.discord_to_telegram: Dict[str, Tuple[int, str, int]] = {}
        # Maps Telegram message IDs to Discord message info (msg_id, username, user_id)
        self.telegram_to_discord: Dict[int, Tuple[str, str, int]] = {}

        # For webhook messages (don't have real IDs, so we use timestamps)
        self.webhook_to_telegram: Dict[str, int] = {}  # webhook_timestamp -> telegram_msg_id
        self.telegram_to_webhook: Dict[int, str] = {}  # telegram_msg_id -> webhook_timestamp

        # Offset for Telegram polling to track processed updates
        self.telegram_offset = 0

        # Setup Discord event handlers
        self.setup_discord_events()

    def setup_discord_events(self):
        """Setup all Discord bot event handlers"""
        
        @self.discord_bot.event
        async def on_ready():
            """Called when Discord bot is ready and connected"""
            logger.info(f'{self.discord_bot.user} connected to Discord!')
            # Start Telegram polling in background
            asyncio.create_task(self.telegram_polling())

        @self.discord_bot.event
        async def on_message(message):
            """Handle incoming Discord messages"""
            # Ignore messages from the bot itself
            if message.author == self.discord_bot.user:
                return

            # Ignore webhook messages (messages from Telegram)
            if message.webhook_id:
                return

            # Only process messages from the configured channel
            if message.channel.id == self.discord_channel_id:
                await self.handle_discord_message(message)

        @self.discord_bot.event
        async def on_message_delete(message):
            """Handle Discord message deletions"""
            # Ignore webhook messages
            if message.webhook_id:
                return

            # Only process deletions from the configured channel
            if message.channel.id == self.discord_channel_id:
                await self.handle_discord_message_delete(message)

    async def handle_discord_message_delete(self, message):
        """
        Handle deletion of Discord messages by deleting the corresponding Telegram message.
        
        Args:
            message: The deleted Discord message object
        """
        try:
            message_id = str(message.id)
            if message_id in self.discord_to_telegram:
                telegram_msg_id = self.discord_to_telegram[message_id][0]

                # Delete corresponding message in Telegram
                result = await self.telegram_bot.delete_message(self.telegram_chat_id, telegram_msg_id)

                if result.get('ok'):
                    # Remove from mapping dictionaries
                    del self.discord_to_telegram[message_id]
                    if telegram_msg_id in self.telegram_to_discord:
                        del self.telegram_to_discord[telegram_msg_id]
                    logger.info(f"Message deleted in Telegram: {telegram_msg_id}")
                else:
                    logger.warning(f"Failed to delete message in Telegram: {result}")

        except Exception as e:
            logger.error(f"Error deleting message in Telegram: {e}")

    async def handle_discord_message(self, message):
        """
        Process Discord messages and forward them to Telegram.
        Handles text, attachments, and replies.
        
        Args:
            message: The Discord message object to process
        """
        try:
            # Prepare message text with user information
            text = f"💬 <b>{message.author.display_name}</b>: {message.content}"

            # Check if this is a reply to another message
            reply_to = None
            if message.reference and message.reference.message_id:
                discord_msg_id = str(message.reference.message_id)
                if discord_msg_id in self.discord_to_telegram:
                    reply_to = self.discord_to_telegram[discord_msg_id][0]  # Get telegram_msg_id

            # Send text message if there's content
            telegram_msg = None
            if message.content:
                telegram_msg = await self.telegram_bot.send_message(
                    self.telegram_chat_id, text, reply_to
                )

            # Process attachments - send directly without additional text message
            for attachment in message.attachments:
                caption = ""
                if message.content:
                    caption = f"<b>{message.author.display_name}</b>: {message.content}"

                # Determine attachment type and send accordingly
                if attachment.content_type:
                    if attachment.content_type.startswith('image/'):
                        telegram_msg = await self.telegram_bot.send_photo(
                            self.telegram_chat_id, attachment.url, caption, reply_to
                        )
                    elif attachment.content_type.startswith('video/'):
                        telegram_msg = await self.telegram_bot.send_video(
                            self.telegram_chat_id, attachment.url, caption, reply_to
                        )
                    else:
                        telegram_msg = await self.telegram_bot.send_document(
                            self.telegram_chat_id, attachment.url, caption, reply_to
                        )
                else:
                    # Default to document if content type is unknown
                    telegram_msg = await self.telegram_bot.send_document(
                        self.telegram_chat_id, attachment.url, caption, reply_to
                    )

            # Map messages for future replies and deletions
            if telegram_msg and telegram_msg.get('ok'):
                telegram_msg_id = telegram_msg['result']['message_id']
                self.discord_to_telegram[str(message.id)] = (telegram_msg_id, message.author.display_name, message.author.id)
                self.telegram_to_discord[telegram_msg_id] = (str(message.id), message.author.display_name, message.author.id)

        except Exception as e:
            logger.error(f"Error processing Discord message: {e}")

    async def handle_telegram_message_delete(self, update):
        """
        Process Telegram message deletions and delete corresponding Discord messages.
        
        Args:
            update: Telegram update containing deletion information
        """
        try:
            deleted_msg = update.get('deleted_message', {})
            if not deleted_msg:
                return

            message_id = deleted_msg.get('message_id')
            if not message_id:
                return

            # Check if we have mapping for this message
            if message_id in self.telegram_to_discord:
                discord_msg_id, username, user_id = self.telegram_to_discord[message_id]

                try:
                    # Find and delete message in Discord
                    channel = self.discord_bot.get_channel(self.discord_channel_id)
                    if channel:
                        # For webhooks, we can't delete directly
                        # So we try to find and delete via webhook
                        await self.delete_webhook_message(discord_msg_id)

                    # Remove from mapping dictionaries
                    del self.telegram_to_discord[message_id]
                    if discord_msg_id in self.discord_to_telegram:
                        del self.discord_to_telegram[discord_msg_id]

                    logger.info(f"Message deleted in Discord: {discord_msg_id}")

                except Exception as e:
                    logger.error(f"Error deleting message in Discord: {e}")

            elif message_id in self.telegram_to_webhook:
                # Remove webhook mapping
                webhook_id = self.telegram_to_webhook[message_id]
                del self.telegram_to_webhook[message_id]
                if webhook_id in self.webhook_to_telegram:
                    del self.webhook_to_telegram[webhook_id]

        except Exception as e:
            logger.error(f"Error processing Telegram deletion: {e}")

    async def delete_webhook_message(self, message_identifier: str):
        """
        Attempt to delete a message sent via webhook using Discord API.
        
        Args:
            message_identifier: The identifier of the webhook message to delete
        """
        try:
            # For webhooks, we try to delete via Discord API
            # This requires having the real message ID
            webhook_id, webhook_token = self.extract_webhook_info(self.webhook_url)

            if webhook_id and webhook_token:
                url = f"https://discord.com/api/webhooks/{webhook_id}/{webhook_token}/messages/{message_identifier}"

                async with aiohttp.ClientSession() as session:
                    async with session.delete(url) as response:
                        if response.status == 204:
                            logger.info(f"Webhook message deleted: {message_identifier}")
                        else:
                            logger.warning(f"Failed to delete webhook message: {response.status}")

        except Exception as e:
            logger.error(f"Error deleting webhook message: {e}")

    def extract_webhook_info(self, webhook_url: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Extract webhook ID and token from webhook URL.
        
        Args:
            webhook_url: The Discord webhook URL
            
        Returns:
            Tuple containing webhook ID and token, or (None, None) if extraction fails
        """
        try:
            # URL format: https://discord.com/api/webhooks/{id}/{token}
            parts = webhook_url.split('/')
            if len(parts) >= 2:
                webhook_id = parts[-2]
                webhook_token = parts[-1]
                return webhook_id, webhook_token
        except:
            pass
        return None, None

    async def handle_telegram_message(self, update):
        """
        Process Telegram messages and forward them to Discord via webhook.
        Handles various message types including text, photos, videos, documents, voice, stickers.
        
        Args:
            update: Telegram update containing message information
        """
        try:
            # Check if this is a message deletion
            if 'deleted_message' in update:
                await self.handle_telegram_message_delete(update)
                return

            message = update.get('message', {})
            if not message:
                return

            user = message.get('from', {})
            chat = message.get('chat', {})

            # Check if message is from the correct chat
            if chat.get('id') != self.telegram_chat_id:
                return

            # Get user information
            username = user.get('username', user.get('first_name', 'User'))
            user_id = user.get('id')

            # Download profile picture correctly
            avatar_url = await self.get_telegram_user_avatar(user_id)

            # Prepare webhook data
            webhook_data = {
                'username': username,
                'avatar_url': avatar_url,
                'content': ''
            }

            # Check if this is a reply to another message
            reply_text = ""
            if message.get('reply_to_message'):
                replied_msg_id = message['reply_to_message']['message_id']
                if replied_msg_id in self.telegram_to_discord:
                    discord_msg_id, original_username, original_user_id = self.telegram_to_discord[replied_msg_id]
                    reply_text = f"> 💬 Replying to **{original_username}**\n\n"
                elif replied_msg_id in self.telegram_to_webhook:
                    webhook_id = self.telegram_to_webhook[replied_msg_id]
                    reply_text = f"> 💬 Replying to previous message\n\n"

            # Process different types of messages
            discord_msg = None
            message_id = message.get('message_id')

            if message.get('text'):
                # Handle text messages
                webhook_data['content'] = reply_text + message['text']
                discord_msg = await self.send_webhook_message(webhook_data)

            elif message.get('photo'):
                # Handle photo messages - get highest resolution
                photo = max(message['photo'], key=lambda p: p.get('width', 0))
                file_path = await self.download_telegram_file(photo['file_id'])

                # Send directly without additional message
                caption = message.get('caption', '')
                if caption:
                    webhook_data['content'] = reply_text + caption
                else:
                    webhook_data['content'] = reply_text

                discord_msg = await self.send_webhook_message(webhook_data, file_path)

                # Clean up temporary file
                if file_path and os.path.exists(file_path):
                    os.remove(file_path)

            elif message.get('video'):
                # Handle video messages
                file_path = await self.download_telegram_file(message['video']['file_id'])
                caption = message.get('caption', '')
                if caption:
                    webhook_data['content'] = reply_text + caption
                else:
                    webhook_data['content'] = reply_text

                discord_msg = await self.send_webhook_message(webhook_data, file_path)

                # Clean up temporary file
                if file_path and os.path.exists(file_path):
                    os.remove(file_path)

            elif message.get('document'):
                # Handle document messages
                file_path = await self.download_telegram_file(message['document']['file_id'])
                caption = message.get('caption', '')
                if caption:
                    webhook_data['content'] = reply_text + caption
                else:
                    webhook_data['content'] = reply_text

                discord_msg = await self.send_webhook_message(webhook_data, file_path)

                # Clean up temporary file
                if file_path and os.path.exists(file_path):
                    os.remove(file_path)

            elif message.get('voice'):
                # Handle voice messages
                file_path = await self.download_telegram_file(message['voice']['file_id'])
                webhook_data['content'] = reply_text + '🎤 Audio'
                discord_msg = await self.send_webhook_message(webhook_data, file_path)

                # Clean up temporary file
                if file_path and os.path.exists(file_path):
                    os.remove(file_path)

            elif message.get('animation'):  # Handle GIFs
                file_path = await self.download_telegram_file(message['animation']['file_id'])
                caption = message.get('caption', '')
                webhook_data['content'] = reply_text + caption
                discord_msg = await self.send_webhook_message(webhook_data, file_path)

                # Clean up temporary file
                if file_path and os.path.exists(file_path):
                    os.remove(file_path)

            elif message.get('sticker'):
                # Handle sticker messages
                # Download sticker as image - send directly
                sticker = message['sticker']
                file_path = None

                if sticker.get('is_animated') or sticker.get('is_video'):
                    # For animated/video stickers, use thumbnail if available
                    if sticker.get('thumbnail'):
                        file_path = await self.download_telegram_file(sticker['thumbnail']['file_id'])

                    if not file_path:
                        webhook_data['content'] = reply_text + f"🎭 {sticker.get('emoji', '📷')}"
                        discord_msg = await self.send_webhook_message(webhook_data)
                else:
                    # For static stickers
                    file_path = await self.download_telegram_file(sticker['file_id'])

                if file_path:
                    webhook_data['content'] = reply_text
                    discord_msg = await self.send_webhook_message(webhook_data, file_path)

                    # Clean up temporary file
                    if os.path.exists(file_path):
                        os.remove(file_path)

            # Map messages for future replies and deletions
            if discord_msg and message_id:
                webhook_timestamp = discord_msg.id
                self.telegram_to_webhook[message_id] = webhook_timestamp
                self.webhook_to_telegram[webhook_timestamp] = message_id

        except Exception as e:
            logger.error(f"Error processing Telegram message: {e}")

    async def get_telegram_user_avatar(self, user_id: int) -> str:
        """
        Get user's profile picture from Telegram.
        
        Args:
            user_id: The Telegram user ID
            
        Returns:
            URL of the user's avatar, or a default avatar if none found
        """
        try:
            await self.telegram_bot.init_session()

            # Get user profile photos
            async with self.telegram_bot.session.get(
                f"{self.telegram_bot.api_url}/getUserProfilePhotos",
                params={'user_id': user_id, 'limit': 1}
            ) as response:
                data = await response.json()

            if data.get('ok') and data['result']['total_count'] > 0:
                # Get the first photo (highest resolution)
                photo = data['result']['photos'][0][-1]
                file_url = await self.get_telegram_file_url(photo['file_id'])
                return file_url

            # Default avatar if no photo available
            return f"https://api.dicebear.com/7.x/initials/svg?seed={user_id}"

        except Exception as e:
            logger.error(f"Error fetching avatar: {e}")
            return f"https://api.dicebear.com/7.x/initials/svg?seed={user_id}"

    async def get_telegram_file_url(self, file_id: str) -> str:
        """
        Get the download URL for a Telegram file.
        
        Args:
            file_id: The file ID from Telegram
            
        Returns:
            Direct URL to download the file
        """
        try:
            await self.telegram_bot.init_session()

            async with self.telegram_bot.session.get(
                f"{self.telegram_bot.api_url}/getFile",
                params={'file_id': file_id}
            ) as response:
                data = await response.json()

            if data.get('ok'):
                file_path = data['result']['file_path']
                return f"https://api.telegram.org/file/bot{self.telegram_token}/{file_path}"

            return ""

        except Exception as e:
            logger.error(f"Error getting file URL: {e}")
            return ""

    async def download_telegram_file(self, file_id: str) -> Optional[str]:
        """
        Download a file from Telegram and return the local file path.
        
        Args:
            file_id: The file ID from Telegram
            
        Returns:
            Path to the downloaded temporary file, or None if download failed
        """
        try:
            await self.telegram_bot.init_session()

            # Get file information
            async with self.telegram_bot.session.get(
                f"{self.telegram_bot.api_url}/getFile",
                params={'file_id': file_id}
            ) as response:
                data = await response.json()

            if not data.get('ok'):
                return None

            file_path = data['result']['file_path']
            file_url = f"https://api.telegram.org/file/bot{self.telegram_token}/{file_path}"

            # Download file
            async with self.telegram_bot.session.get(file_url) as response:
                if response.status != 200:
                    return None

                # Create temporary file
                file_extension = os.path.splitext(file_path)[1]
                temp_file = tempfile.mktemp(suffix=file_extension)

                with open(temp_file, 'wb') as f:
                    f.write(await response.read())

                return temp_file

        except Exception as e:
            logger.error(f"Error downloading file from Telegram: {e}")
            return None

    async def send_webhook_message(self, webhook_data: dict, file_path: str = None):
        """
        Send a message to Discord using a webhook.
        
        Args:
            webhook_data: Dictionary containing webhook payload (username, avatar_url, content)
            file_path: Optional path to file to attach to the message
            
        Returns:
            Mock message object with ID, or None if sending failed
        """
        try:
            async with aiohttp.ClientSession() as session:
                if file_path and os.path.exists(file_path):
                    # Send file attachment
                    with open(file_path, 'rb') as f:
                        filename = os.path.basename(file_path)
                        form = aiohttp.FormData()
                        form.add_field('payload_json', json.dumps(webhook_data))
                        form.add_field('file', f, filename=filename)

                        async with session.post(self.webhook_url, data=form) as response:
                            if response.status in [200, 204]:
                                # Get sent message data
                                response_data = await response.json()
                                # Simulate message object with real ID
                                class MockMessage:
                                    def __init__(self, msg_id):
                                        self.id = msg_id

                                # Use response ID if available
                                msg_id = response_data.get('id', f"webhook_{datetime.now().timestamp()}")
                                return MockMessage(msg_id)
                else:
                    # Send text only
                    async with session.post(self.webhook_url, json=webhook_data) as response:
                        if response.status in [200, 204]:
                            # Get sent message data
                            response_data = await response.json()
                            class MockMessage:
                                def __init__(self, msg_id):
                                    self.id = msg_id

                            # Use response ID if available
                            msg_id = response_data.get('id', f"webhook_{datetime.now().timestamp()}")
                            return MockMessage(msg_id)

        except Exception as e:
            logger.error(f"Error sending webhook: {e}")
            return None

    async def telegram_polling(self):
        """
        Continuously poll Telegram for new updates.
        This runs in the background to receive messages from Telegram.
        """
        while True:
            try:
                # Get updates from Telegram
                updates = await self.telegram_bot.get_updates(self.telegram_offset)

                if updates.get('ok'):
                    for update in updates['result']:
                        await self.handle_telegram_message(update)
                        # Update offset to acknowledge processed update
                        self.telegram_offset = update['update_id'] + 1

                await asyncio.sleep(1)  # Small delay between polling requests

            except Exception as e:
                logger.error(f"Error in Telegram polling: {e}")
                await asyncio.sleep(5)  # Longer delay on error

    async def start(self):
        """
        Start the Discord bot and begin synchronization.
        This is the main entry point for the application.
        """
        try:
            await self.discord_bot.start(self.discord_token)
        except Exception as e:
            logger.error(f"Error starting: {e}")
        finally:
            # Clean up Telegram session
            await self.telegram_bot.close_session()

# Example usage
if __name__ == "__main__":
    # Configuration settings
    DISCORD_TOKEN = "YOUR DISCORD BOT TOKEN"
    TELEGRAM_TOKEN = "YOUR TELEGRAM BOT TOKEN"
    WEBHOOK_URL = "https://discord.com/api/webhooks/YOUR_WEBHOOK_URL"
    DISCORD_CHANNEL_ID = 123456789  # Discord channel ID
    TELEGRAM_CHAT_ID = -123456789  # Telegram group ID (negative number for groups)

    # Create and start the synchronization system
    sync_system = DiscordTelegramSync(
        discord_token=DISCORD_TOKEN,
        telegram_token=TELEGRAM_TOKEN,
        webhook_url=WEBHOOK_URL,
        discord_channel_id=DISCORD_CHANNEL_ID,
        telegram_chat_id=TELEGRAM_CHAT_ID
    )

    # Run the application
    asyncio.run(sync_system.start())

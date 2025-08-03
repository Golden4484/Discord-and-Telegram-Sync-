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

# Configuração de logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TelegramBot:
    def __init__(self, token: str):
        self.token = token
        self.api_url = f"https://api.telegram.org/bot{token}"
        self.session = None
        
    async def init_session(self):
        if not self.session:
            self.session = aiohttp.ClientSession()
    
    async def close_session(self):
        if self.session:
            await self.session.close()
    
    async def send_message(self, chat_id: int, text: str, reply_to_message_id: Optional[int] = None):
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
        await self.init_session()
        data = {
            'chat_id': chat_id,
            'message_id': message_id
        }
        async with self.session.post(f"{self.api_url}/deleteMessage", data=data) as response:
            return await response.json()
    
    async def get_updates(self, offset: int = 0):
        await self.init_session()
        params = {'offset': offset, 'timeout': 30}
        async with self.session.get(f"{self.api_url}/getUpdates", params=params) as response:
            return await response.json()

class DiscordTelegramSync:
    def __init__(self, discord_token: str, telegram_token: str, webhook_url: str, 
                 discord_channel_id: int, telegram_chat_id: int):
        # Configurações
        self.discord_token = discord_token
        self.telegram_token = telegram_token
        self.webhook_url = webhook_url
        self.discord_channel_id = discord_channel_id
        self.telegram_chat_id = telegram_chat_id
        
        # Bots
        intents = discord.Intents.default()
        intents.message_content = True
        self.discord_bot = commands.Bot(command_prefix='!', intents=intents)
        self.telegram_bot = TelegramBot(telegram_token)
        
        # Mapeamento bidirecional de mensagens
        self.discord_to_telegram: Dict[str, Tuple[int, str, int]] = {}  # discord_msg_id -> (telegram_msg_id, username, user_id)
        self.telegram_to_discord: Dict[int, Tuple[str, str, int]] = {}  # telegram_msg_id -> (discord_msg_id, username, user_id)
        
        # Para webhooks (não têm ID real, então usamos timestamp)
        self.webhook_to_telegram: Dict[str, int] = {}  # webhook_timestamp -> telegram_msg_id
        self.telegram_to_webhook: Dict[int, str] = {}  # telegram_msg_id -> webhook_timestamp
        
        # Offset para Telegram
        self.telegram_offset = 0
        
        # Setup dos eventos
        self.setup_discord_events()
    
    def setup_discord_events(self):
        @self.discord_bot.event
        async def on_ready():
            logger.info(f'{self.discord_bot.user} conectado ao Discord!')
            # Inicia o polling do Telegram
            asyncio.create_task(self.telegram_polling())
        
        @self.discord_bot.event
        async def on_message(message):
            if message.author == self.discord_bot.user:
                return
            
            # Ignorar webhooks (mensagens do Telegram)
            if message.webhook_id:
                return
            
            if message.channel.id == self.discord_channel_id:
                await self.handle_discord_message(message)
        
        @self.discord_bot.event
        async def on_message_delete(message):
            if message.webhook_id:
                return
            
            if message.channel.id == self.discord_channel_id:
                await self.handle_discord_message_delete(message)
    
    async def handle_discord_message_delete(self, message):
        """Deletar mensagem correspondente no Telegram"""
        try:
            message_id = str(message.id)
            if message_id in self.discord_to_telegram:
                telegram_msg_id = self.discord_to_telegram[message_id][0]
                
                # Deletar mensagem no Telegram
                result = await self.telegram_bot.delete_message(self.telegram_chat_id, telegram_msg_id)
                
                if result.get('ok'):
                    # Remover dos mapeamentos
                    del self.discord_to_telegram[message_id]
                    if telegram_msg_id in self.telegram_to_discord:
                        del self.telegram_to_discord[telegram_msg_id]
                    logger.info(f"Mensagem deletada no Telegram: {telegram_msg_id}")
                else:
                    logger.warning(f"Falha ao deletar mensagem no Telegram: {result}")
        
        except Exception as e:
            logger.error(f"Erro ao deletar mensagem no Telegram: {e}")
    
    async def handle_discord_message(self, message):
        try:
            # Preparar texto
            text = f"💬 <b>{message.author.display_name}</b>: {message.content}"
            
            # Verificar se é reply
            reply_to = None
            if message.reference and message.reference.message_id:
                discord_msg_id = str(message.reference.message_id)
                if discord_msg_id in self.discord_to_telegram:
                    reply_to = self.discord_to_telegram[discord_msg_id][0]  # telegram_msg_id
            
            # Enviar texto se houver
            telegram_msg = None
            if message.content:
                telegram_msg = await self.telegram_bot.send_message(
                    self.telegram_chat_id, text, reply_to
                )
            
            # Processar anexos - enviar diretamente sem mensagem de texto adicional
            for attachment in message.attachments:
                caption = ""
                if message.content:
                    caption = f"<b>{message.author.display_name}</b>: {message.content}"
                
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
                    telegram_msg = await self.telegram_bot.send_document(
                        self.telegram_chat_id, attachment.url, caption, reply_to
                    )
            
            # Mapear mensagens para replies futuros e deleções
            if telegram_msg and telegram_msg.get('ok'):
                telegram_msg_id = telegram_msg['result']['message_id']
                self.discord_to_telegram[str(message.id)] = (telegram_msg_id, message.author.display_name, message.author.id)
                self.telegram_to_discord[telegram_msg_id] = (str(message.id), message.author.display_name, message.author.id)
        
        except Exception as e:
            logger.error(f"Erro ao processar mensagem do Discord: {e}")
    
    async def handle_telegram_message_delete(self, update):
        """Processar deleção de mensagem do Telegram"""
        try:
            deleted_msg = update.get('deleted_message', {})
            if not deleted_msg:
                return
            
            message_id = deleted_msg.get('message_id')
            if not message_id:
                return
            
            # Verificar se temos mapeamento para essa mensagem
            if message_id in self.telegram_to_discord:
                discord_msg_id, username, user_id = self.telegram_to_discord[message_id]
                
                try:
                    # Buscar e deletar mensagem no Discord
                    channel = self.discord_bot.get_channel(self.discord_channel_id)
                    if channel:
                        # Para webhooks, não podemos deletar diretamente
                        # Então vamos tentar encontrar e deletar via webhook
                        await self.delete_webhook_message(discord_msg_id)
                    
                    # Remover dos mapeamentos
                    del self.telegram_to_discord[message_id]
                    if discord_msg_id in self.discord_to_telegram:
                        del self.discord_to_telegram[discord_msg_id]
                    
                    logger.info(f"Mensagem deletada no Discord: {discord_msg_id}")
                
                except Exception as e:
                    logger.error(f"Erro ao deletar mensagem no Discord: {e}")
            
            elif message_id in self.telegram_to_webhook:
                # Remover mapeamento de webhook
                webhook_id = self.telegram_to_webhook[message_id]
                del self.telegram_to_webhook[message_id]
                if webhook_id in self.webhook_to_telegram:
                    del self.webhook_to_telegram[webhook_id]
        
        except Exception as e:
            logger.error(f"Erro ao processar deleção do Telegram: {e}")
    
    async def delete_webhook_message(self, message_identifier: str):
        """Tentar deletar mensagem enviada via webhook"""
        try:
            # Para webhooks, tentamos deletar via API do Discord
            # Isso requer que tenhamos o ID real da mensagem
            webhook_id, webhook_token = self.extract_webhook_info(self.webhook_url)
            
            if webhook_id and webhook_token:
                url = f"https://discord.com/api/webhooks/{webhook_id}/{webhook_token}/messages/{message_identifier}"
                
                async with aiohttp.ClientSession() as session:
                    async with session.delete(url) as response:
                        if response.status == 204:
                            logger.info(f"Mensagem webhook deletada: {message_identifier}")
                        else:
                            logger.warning(f"Falha ao deletar mensagem webhook: {response.status}")
        
        except Exception as e:
            logger.error(f"Erro ao deletar mensagem webhook: {e}")
    
    def extract_webhook_info(self, webhook_url: str) -> Tuple[Optional[str], Optional[str]]:
        """Extrair ID e token do webhook da URL"""
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
        try:
            # Verificar se é uma deleção de mensagem
            if 'deleted_message' in update:
                await self.handle_telegram_message_delete(update)
                return
            
            message = update.get('message', {})
            if not message:
                return
            
            user = message.get('from', {})
            chat = message.get('chat', {})
            
            # Verificar se é do chat correto
            if chat.get('id') != self.telegram_chat_id:
                return
            
            # Obter informações do usuário
            username = user.get('username', user.get('first_name', 'Usuário'))
            user_id = user.get('id')
            
            # Baixar foto do perfil corretamente
            avatar_url = await self.get_telegram_user_avatar(user_id)
            
            # Preparar dados do webhook
            webhook_data = {
                'username': username,
                'avatar_url': avatar_url,
                'content': ''
            }
            
            # Verificar se é reply
            reply_text = ""
            if message.get('reply_to_message'):
                replied_msg_id = message['reply_to_message']['message_id']
                if replied_msg_id in self.telegram_to_discord:
                    discord_msg_id, original_username, original_user_id = self.telegram_to_discord[replied_msg_id]
                    reply_text = f"> 💬 Respondendo à **{original_username}**\n\n"
                elif replied_msg_id in self.telegram_to_webhook:
                    webhook_id = self.telegram_to_webhook[replied_msg_id]
                    reply_text = f"> 💬 Respondendo à mensagem anterior\n\n"
            
            # Processar diferentes tipos de mensagem
            discord_msg = None
            message_id = message.get('message_id')
            
            if message.get('text'):
                webhook_data['content'] = reply_text + message['text']
                discord_msg = await self.send_webhook_message(webhook_data)
            
            elif message.get('photo'):
                # Pegar a maior resolução da foto
                photo = max(message['photo'], key=lambda p: p.get('width', 0))
                file_path = await self.download_telegram_file(photo['file_id'])
                
                # Enviar direto sem mensagem adicional
                caption = message.get('caption', '')
                if caption:
                    webhook_data['content'] = reply_text + caption
                else:
                    webhook_data['content'] = reply_text
                    
                discord_msg = await self.send_webhook_message(webhook_data, file_path)
                
                # Limpar arquivo temporário
                if file_path and os.path.exists(file_path):
                    os.remove(file_path)
            
            elif message.get('video'):
                file_path = await self.download_telegram_file(message['video']['file_id'])
                caption = message.get('caption', '')
                if caption:
                    webhook_data['content'] = reply_text + caption
                else:
                    webhook_data['content'] = reply_text
                    
                discord_msg = await self.send_webhook_message(webhook_data, file_path)
                
                # Limpar arquivo temporário
                if file_path and os.path.exists(file_path):
                    os.remove(file_path)
            
            elif message.get('document'):
                file_path = await self.download_telegram_file(message['document']['file_id'])
                caption = message.get('caption', '')
                if caption:
                    webhook_data['content'] = reply_text + caption
                else:
                    webhook_data['content'] = reply_text
                    
                discord_msg = await self.send_webhook_message(webhook_data, file_path)
                
                # Limpar arquivo temporário
                if file_path and os.path.exists(file_path):
                    os.remove(file_path)
            
            elif message.get('voice'):
                file_path = await self.download_telegram_file(message['voice']['file_id'])
                webhook_data['content'] = reply_text + '🎤 Áudio'
                discord_msg = await self.send_webhook_message(webhook_data, file_path)
                
                # Limpar arquivo temporário
                if file_path and os.path.exists(file_path):
                    os.remove(file_path)
            
            elif message.get('animation'):  # GIFs
                file_path = await self.download_telegram_file(message['animation']['file_id'])
                caption = message.get('caption', '')
                webhook_data['content'] = reply_text + caption
                discord_msg = await self.send_webhook_message(webhook_data, file_path)
                
                # Limpar arquivo temporário
                if file_path and os.path.exists(file_path):
                    os.remove(file_path)
            
            elif message.get('sticker'):
                # Baixar sticker como imagem - enviar direto
                sticker = message['sticker']
                file_path = None
                
                if sticker.get('is_animated') or sticker.get('is_video'):
                    # Para stickers animados/vídeo, usar thumbnail se disponível
                    if sticker.get('thumbnail'):
                        file_path = await self.download_telegram_file(sticker['thumbnail']['file_id'])
                    
                    if not file_path:
                        webhook_data['content'] = reply_text + f"🎭 {sticker.get('emoji', '📷')}"
                        discord_msg = await self.send_webhook_message(webhook_data)
                else:
                    # Para stickers estáticos
                    file_path = await self.download_telegram_file(sticker['file_id'])
                
                if file_path:
                    webhook_data['content'] = reply_text
                    discord_msg = await self.send_webhook_message(webhook_data, file_path)
                    
                    # Limpar arquivo temporário
                    if os.path.exists(file_path):
                        os.remove(file_path)
            
            # Mapear mensagens para replies futuros e deleções
            if discord_msg and message_id:
                webhook_timestamp = discord_msg.id
                self.telegram_to_webhook[message_id] = webhook_timestamp
                self.webhook_to_telegram[webhook_timestamp] = message_id
        
        except Exception as e:
            logger.error(f"Erro ao processar mensagem do Telegram: {e}")
    
    async def get_telegram_user_avatar(self, user_id: int) -> str:
        """Corrigida a função para buscar avatar do usuário"""
        try:
            await self.telegram_bot.init_session()
            
            # Buscar fotos do perfil
            async with self.telegram_bot.session.get(
                f"{self.telegram_bot.api_url}/getUserProfilePhotos",
                params={'user_id': user_id, 'limit': 1}
            ) as response:
                data = await response.json()
            
            if data.get('ok') and data['result']['total_count'] > 0:
                # Pegar a primeira foto
                photo = data['result']['photos'][0][-1]  # Maior resolução
                file_url = await self.get_telegram_file_url(photo['file_id'])
                return file_url
            
            # Avatar padrão se não houver foto
            return f"https://api.dicebear.com/7.x/initials/svg?seed={user_id}"
        
        except Exception as e:
            logger.error(f"Erro ao buscar avatar: {e}")
            return f"https://api.dicebear.com/7.x/initials/svg?seed={user_id}"
    
    async def get_telegram_file_url(self, file_id: str) -> str:
        """Obter URL do arquivo do Telegram"""
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
            logger.error(f"Erro ao obter URL do arquivo: {e}")
            return ""
    
    async def download_telegram_file(self, file_id: str) -> Optional[str]:
        """Baixa arquivo do Telegram e retorna o caminho local"""
        try:
            await self.telegram_bot.init_session()
            
            # Obter informações do arquivo
            async with self.telegram_bot.session.get(
                f"{self.telegram_bot.api_url}/getFile",
                params={'file_id': file_id}
            ) as response:
                data = await response.json()
            
            if not data.get('ok'):
                return None
            
            file_path = data['result']['file_path']
            file_url = f"https://api.telegram.org/file/bot{self.telegram_token}/{file_path}"
            
            # Baixar arquivo
            async with self.telegram_bot.session.get(file_url) as response:
                if response.status != 200:
                    return None
                
                # Criar arquivo temporário
                file_extension = os.path.splitext(file_path)[1]
                temp_file = tempfile.mktemp(suffix=file_extension)
                
                with open(temp_file, 'wb') as f:
                    f.write(await response.read())
                
                return temp_file
        
        except Exception as e:
            logger.error(f"Erro ao baixar arquivo do Telegram: {e}")
            return None
    
    async def send_webhook_message(self, webhook_data: dict, file_path: str = None):
        try:
            async with aiohttp.ClientSession() as session:
                if file_path and os.path.exists(file_path):
                    # Enviar arquivo
                    with open(file_path, 'rb') as f:
                        filename = os.path.basename(file_path)
                        form = aiohttp.FormData()
                        form.add_field('payload_json', json.dumps(webhook_data))
                        form.add_field('file', f, filename=filename)
                        
                        async with session.post(self.webhook_url, data=form) as response:
                            if response.status in [200, 204]:
                                # Obter dados da mensagem enviada
                                response_data = await response.json()
                                # Simular objeto de mensagem com ID real
                                class MockMessage:
                                    def __init__(self, msg_id):
                                        self.id = msg_id
                                
                                # Usar ID da resposta se disponível
                                msg_id = response_data.get('id', f"webhook_{datetime.now().timestamp()}")
                                return MockMessage(msg_id)
                else:
                    # Enviar apenas texto
                    async with session.post(self.webhook_url, json=webhook_data) as response:
                        if response.status in [200, 204]:
                            # Obter dados da mensagem enviada
                            response_data = await response.json()
                            class MockMessage:
                                def __init__(self, msg_id):
                                    self.id = msg_id
                            
                            # Usar ID da resposta se disponível
                            msg_id = response_data.get('id', f"webhook_{datetime.now().timestamp()}")
                            return MockMessage(msg_id)
        
        except Exception as e:
            logger.error(f"Erro ao enviar webhook: {e}")
            return None
    
    async def telegram_polling(self):
        while True:
            try:
                updates = await self.telegram_bot.get_updates(self.telegram_offset)
                
                if updates.get('ok'):
                    for update in updates['result']:
                        await self.handle_telegram_message(update)
                        self.telegram_offset = update['update_id'] + 1
                
                await asyncio.sleep(1)
            
            except Exception as e:
                logger.error(f"Erro no polling do Telegram: {e}")
                await asyncio.sleep(5)
    
    async def start(self):
        try:
            await self.discord_bot.start(self.discord_token)
        except Exception as e:
            logger.error(f"Erro ao iniciar: {e}")
        finally:
            await self.telegram_bot.close_session()

# Exemplo de uso
if __name__ == "__main__":
    # Configurações
    DISCORD_TOKEN = "TEU TOKEN "
    TELEGRAM_TOKEN = "TEU TOKEN"
    WEBHOOK_URL = "https://discord.com/api/webhooks/"
    DISCORD_CHANNEL_ID = 123456789  # ID do canal do Discord
    TELEGRAM_CHAT_ID = -123456789  # ID do grupo do Telegram (número negativo)
    
    # Criar e iniciar o sistema
    sync_system = DiscordTelegramSync(
        discord_token=DISCORD_TOKEN,
        telegram_token=TELEGRAM_TOKEN,
        webhook_url=WEBHOOK_URL,
        discord_channel_id=DISCORD_CHANNEL_ID,
        telegram_chat_id=TELEGRAM_CHAT_ID
    )
    
    # Executar
    asyncio.run(sync_system.start())
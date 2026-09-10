import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from .models import Message
from django.contrib.auth.models import User


class ChatConsumer(AsyncWebsocketConsumer):

    async def connect(self):
        self.user = self.scope['user']
        self.other_user_username = self.scope['url_route']['kwargs']['room_name']

        if not self.user.is_authenticated:
            await self.close()
            return

        users = sorted([self.user.username, self.other_user_username])
        self.room_group_name = f'chat_{users[0]}_{users[1]}'

        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )

        # Every socket also joins "everyone" so profile_update events
        # broadcast from views_profile.py reach all connected users at once.
        await self.channel_layer.group_add(
            'everyone',
            self.channel_name
        )

        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )
        await self.channel_layer.group_discard(
            'everyone',
            self.channel_name
        )

    async def receive(self, text_data):
        data = json.loads(text_data)

        message = data.get('message')
        is_typing = data.get('type') == 'typing'

        if is_typing:
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'typing_status',
                    'sender': self.user.username
                }
            )
            return

        if message:
            await self.save_message(message)

            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'chat_message',
                    'message': message,
                    'sender': self.user.username
                }
            )

    async def chat_message(self, event):
        await self.send(text_data=json.dumps({
            'type': 'chat_message',
            'message': event['message'],
            'sender': event['sender']
        }))

    async def typing_status(self, event):
        await self.send(text_data=json.dumps({
            'type': 'typing',
            'sender': event['sender']
        }))

    async def profile_update(self, event):
        """
        Receives a profile_update event from the channel layer (sent by
        views_profile._broadcast_profile) and forwards it to the browser.

        The browser's applyProfileUpdate() function then patches every
        spot on the page where this user's name or avatar appears.
        """
        await self.send(text_data=json.dumps({
            'type':         'profile_update',
            'username':     event['username'],
            'display_name': event['display_name'],
            'photo_url':    event['photo_url'],
        }))

    @database_sync_to_async
    def save_message(self, message):
        try:
            other_user = User.objects.get(username=self.other_user_username)
            Message.objects.create(
                sender=self.user,
                receiver=other_user,
                message=message
            )
        except User.DoesNotExist:
            pass
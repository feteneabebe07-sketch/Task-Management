# pm/consumers.py - Simplified version
import json
import logging
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth.models import User

logger = logging.getLogger(__name__)

class MessageConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.user = self.scope.get('user')
        
        if not self.user or not self.user.is_authenticated:
            await self.close()
            return
        
        # Create user-specific room name
        self.room_name = f'user_{self.user.id}'
        self.room_group_name = f'chat_{self.room_name}'
        
        # Join room group
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        
        await self.accept()
        logger.info(f'WebSocket connected for user {self.user.id}')
        
        # Send connection confirmation
        await self.send(text_data=json.dumps({
            'type': 'connection_established',
            'message': 'Connected successfully'
        }))
    
    async def disconnect(self, close_code):
        # Leave room group
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )
        logger.info(f'WebSocket disconnected for user {self.user.id}')
    
    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
            message_type = data.get('type')
            
            if message_type == 'direct_message':
                await self.handle_direct_message(data)
            elif message_type == 'typing':
                await self.handle_typing(data)
            elif message_type == 'message_read':
                await self.handle_message_read(data)
                
        except json.JSONDecodeError:
            logger.error('Invalid JSON received')
    
    async def handle_direct_message(self, data):
        """Handle direct message sending"""
        recipient_id = data.get('recipient_id')
        content = data.get('content')
        
        if not recipient_id or not content:
            return
        
        # Save message to database
        message = await self.save_message(recipient_id, content)
        
        # Prepare message data
        message_data = {
            'type': 'direct_message',
            'message_id': message.id,
            'sender_id': self.user.id,
            'sender_name': self.user.get_full_name() or self.user.username,
            'recipient_id': int(recipient_id),
            'content': content,
            'timestamp': message.created_at.isoformat(),
        }
        
        # Send to recipient
        await self.channel_layer.group_send(
            f'chat_user_{recipient_id}',
            {
                'type': 'chat_message',
                'message': message_data
            }
        )
        
        # Also send confirmation to sender
        await self.send(text_data=json.dumps(message_data))
    
    async def handle_typing(self, data):
        """Handle typing indicators"""
        recipient_id = data.get('recipient_id')
        is_typing = data.get('is_typing')
        
        if not recipient_id:
            return
        
        typing_data = {
            'type': 'typing',
            'sender_id': self.user.id,
            'sender_name': self.user.get_full_name() or self.user.username,
            'is_typing': is_typing
        }
        
        # Send typing indicator to recipient
        await self.channel_layer.group_send(
            f'chat_user_{recipient_id}',
            {
                'type': 'chat_typing',
                'message': typing_data
            }
        )
    
    async def handle_message_read(self, data):
        """Handle message read receipts"""
        message_id = data.get('message_id')
        await self.mark_message_as_read(message_id)
    
    # Receive handlers for group messages
    async def chat_message(self, event):
        """Receive message from room group"""
        message = event['message']
        await self.send(text_data=json.dumps(message))
    
    async def chat_typing(self, event):
        """Receive typing indicator from room group"""
        typing_data = event['message']
        await self.send(text_data=json.dumps(typing_data))
    
    # Database operations
    @database_sync_to_async
    def save_message(self, recipient_id, content):
        from core.models import Message
        from django.contrib.auth import get_user_model
        
        User = get_user_model()
        recipient = User.objects.get(id=recipient_id)
        # Prevent duplicate messages: if a message with same sender, content and recipient
        # was created in the last few seconds, return the existing one instead of creating
        from django.utils import timezone
        cutoff = timezone.now() - timezone.timedelta(seconds=5)
        recent = Message.objects.filter(
            sender=self.user,
            content=content,
            created_at__gte=cutoff,
            message_type='direct'
        ).order_by('-created_at')
        if recent.exists():
            msg = recent.first()
            # ensure recipient is attached
            if not msg.recipients.filter(id=recipient.id).exists():
                msg.recipients.add(recipient)
            return msg

        message = Message.objects.create(
            sender=self.user,
            message_type='direct',
            content=content,
        )
        message.recipients.add(recipient)
        return message
    
    @database_sync_to_async
    def mark_message_as_read(self, message_id):
        from core.models import Message
        try:
            message = Message.objects.get(id=message_id)
            message.is_read = True
            message.save()
        except Message.DoesNotExist:
            pass

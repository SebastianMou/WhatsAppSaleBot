from rest_framework import serializers
from app.models import WhatsAppContact, WhatsAppMessage

class WhatsAppContactSerializer(serializers.ModelSerializer):
    message_count = serializers.SerializerMethodField()
    last_message = serializers.SerializerMethodField()
    
    class Meta:
        model = WhatsAppContact
        fields = ['id', 'phone_number', 'name', 'last_interaction', 'message_count', 'last_message']
        read_only_fields = ['last_interaction']
    
    def get_message_count(self, obj):
        """Get total number of messages for this contact"""
        return obj.messages.count()
    
    def get_last_message(self, obj):
        """Get the last message content for this contact"""
        last_message = obj.messages.order_by('-timestamp').first()
        if last_message:
            return {
                'content': last_message.content,
                'timestamp': last_message.timestamp,
                'is_incoming': last_message.is_incoming
            }
        return None

class WhatsAppMessageSerializer(serializers.ModelSerializer):
    contact_name = serializers.CharField(source='contact.name', read_only=True)
    contact_phone = serializers.CharField(source='contact.phone_number', read_only=True)
    
    class Meta:
        model = WhatsAppMessage
        fields = ['id', 'contact', 'contact_name', 'contact_phone', 'content', 
                 'timestamp', 'is_incoming', 'media_url']
        read_only_fields = ['timestamp']
    
    def validate_content(self, value):
        """Ensure message content is not empty"""
        if not value.strip():
            raise serializers.ValidationError("Message content cannot be empty.")
        return value

# Alternative serializer for when you want to create a message with phone number instead of contact ID
class CreateMessageSerializer(serializers.Serializer):
    phone_number = serializers.CharField(max_length=20)
    content = serializers.CharField()
    media_url = serializers.URLField(required=False, allow_blank=True)
    
    def validate_phone_number(self, value):
        """Validate phone number format"""
        # Basic validation - you can make this more sophisticated
        if not value.replace('+', '').replace(' ', '').replace('-', '').isdigit():
            raise serializers.ValidationError("Invalid phone number format.")
        return value

# Serializer for sending messages (used by your Baileys service)
class SendMessageSerializer(serializers.Serializer):
    contact_id = serializers.IntegerField()
    content = serializers.CharField()
    media_url = serializers.URLField(required=False, allow_blank=True)
    
    def validate_contact_id(self, value):
        """Ensure contact exists"""
        from app.models import WhatsAppContact
        try:
            WhatsAppContact.objects.get(id=value)
        except WhatsAppContact.DoesNotExist:
            raise serializers.ValidationError("Contact does not exist.")
        return value

# Serializer for webhook data (when receiving messages from Baileys)
class WebhookMessageSerializer(serializers.Serializer):
    from_number = serializers.CharField(source='from')
    name = serializers.CharField(required=False, allow_blank=True)
    content = serializers.CharField()
    timestamp = serializers.DateTimeField()
    media_url = serializers.URLField(required=False, allow_blank=True)
    
    def validate_from_number(self, value):
        """Clean phone number format"""
        # Remove common formatting characters
        cleaned = value.replace('+', '').replace(' ', '').replace('-', '').replace('(', '').replace(')', '')
        return '+' + cleaned if not value.startswith('+') else value

# Simple serializer for AI reply suggestions (for future use)
class AIReplySuggestionSerializer(serializers.Serializer):
    suggestions = serializers.ListField(
        child=serializers.CharField(),
        max_length=3,  # Limit to 3 suggestions
        min_length=1
    )
    context = serializers.CharField(required=False)
    contact_id = serializers.IntegerField()
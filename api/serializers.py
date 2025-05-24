from rest_framework import serializers
from app.models import WhatsAppContact, WhatsAppMessage, ClientData

class WhatsAppContactSerializer(serializers.ModelSerializer):
    message_count = serializers.SerializerMethodField()
    last_message = serializers.SerializerMethodField()
    has_client_data = serializers.SerializerMethodField()
    
    class Meta:
        model = WhatsAppContact
        fields = ['id', 'phone_number', 'name', 'last_interaction', 'message_count', 'last_message', 'has_client_data']
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
    
    def get_has_client_data(self, obj):
        """Check if contact has associated client data"""
        return obj.client_data.exists()

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

class ClientDataSerializer(serializers.ModelSerializer):
    contact_phone = serializers.CharField(source='contact.phone_number', read_only=True)
    contact_name = serializers.CharField(source='contact.name', read_only=True)
    
    class Meta:
        model = ClientData
        fields = ['id', 'contact', 'contact_phone', 'contact_name', 'fullname', 
                 'email', 'curp', 'rfc', 'address', 'referral_phone_number', 'created_at']
        read_only_fields = ['created_at']
    
    def validate_curp(self, value):
        """Basic CURP validation - 18 characters"""
        if len(value) != 18:
            raise serializers.ValidationError("CURP must be exactly 18 characters.")
        return value.upper()
    
    def validate_rfc(self, value):
        """Basic RFC validation - 12 or 13 characters"""
        if len(value) not in [12, 13]:
            raise serializers.ValidationError("RFC must be 12 or 13 characters.")
        return value.upper()

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

# Nested serializer for complete contact info with client data
class CompleteContactSerializer(serializers.ModelSerializer):
    client_data = ClientDataSerializer(many=True, read_only=True)
    recent_messages = serializers.SerializerMethodField()
    
    class Meta:
        model = WhatsAppContact
        fields = ['id', 'phone_number', 'name', 'last_interaction', 'client_data', 'recent_messages']
    
    def get_recent_messages(self, obj):
        """Get last 10 messages for this contact"""
        recent_messages = obj.messages.order_by('-timestamp')[:10]
        return WhatsAppMessageSerializer(recent_messages, many=True).data
from django.db import models
from django.contrib.auth.models import User

class WhatsAppSession(models.Model):
    session_id = models.CharField(max_length=50, unique=True)  # Remove null=True
    session_name = models.CharField(max_length=100)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='whatsapp_sessions')  # Remove null=True
    phone_number = models.CharField(max_length=20, blank=True, default='')  # Remove null=True, add default
    is_active = models.BooleanField(default=False)  # Remove null=True
    created_at = models.DateTimeField(auto_now_add=True)  # Remove null=True
    
    def __str__(self):
        return f"{self.session_name} ({self.user.username})"

class WhatsAppContact(models.Model):
    phone_number = models.CharField(max_length=20)
    name = models.CharField(max_length=100, blank=True, default='')  # Add default
    last_interaction = models.DateTimeField(auto_now=True)
    session = models.ForeignKey(WhatsAppSession, on_delete=models.CASCADE, related_name='contacts')
    
    class Meta:
        unique_together = ['phone_number', 'session']
    
    def __str__(self):
        return f"{self.name or 'Unknown'} ({self.phone_number}) - {self.session.session_name}"

class WhatsAppMessage(models.Model):
    contact = models.ForeignKey(WhatsAppContact, on_delete=models.CASCADE, related_name='messages')  # Remove null=True
    content = models.TextField(default='')  # Remove null=True, add default
    timestamp = models.DateTimeField()  # Remove null=True
    is_incoming = models.BooleanField(default=True)  # Remove null=True, add default
    media_url = models.URLField(blank=True, default='')  # Remove null=True, add default
    
    class Meta:
        ordering = ['timestamp']

class ClientData(models.Model):
    contact = models.ForeignKey(WhatsAppContact, on_delete=models.CASCADE, related_name='client_data')
    fullname = models.CharField(max_length=100)
    email = models.EmailField(unique=True)
    curp = models.CharField(max_length=18, unique=True) 
    rfc = models.CharField(max_length=13, unique=True)  
    address = models.TextField() 
    phone_number = models.CharField(max_length=20, blank=True, null=True)
    referral_phone_number = models.CharField(max_length=20, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return self.fullname
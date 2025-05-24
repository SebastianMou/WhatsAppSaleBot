from django.db import models

# Create your models here.
class WhatsAppContact(models.Model):
    phone_number = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=100, blank=True)
    last_interaction = models.DateTimeField(auto_now=True)

class WhatsAppMessage(models.Model):
    contact = models.ForeignKey(WhatsAppContact, on_delete=models.CASCADE, related_name='messages')
    content = models.TextField()
    timestamp = models.DateTimeField()
    is_incoming = models.BooleanField()  # True if received, False if sent
    media_url = models.URLField(blank=True, null=True)  # For media messages
    
    class Meta:
        ordering = ['timestamp']

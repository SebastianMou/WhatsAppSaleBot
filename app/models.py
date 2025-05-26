from django.db import models

# Create your models here.
class WhatsAppContact(models.Model):
    phone_number = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=100, blank=True)
    last_interaction = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.name or 'Unknown'} ({self.phone_number})"


class WhatsAppMessage(models.Model):
    contact = models.ForeignKey(WhatsAppContact, on_delete=models.CASCADE, related_name='messages')
    content = models.TextField()
    timestamp = models.DateTimeField()
    is_incoming = models.BooleanField()  # True if received, False if sent
    media_url = models.URLField(blank=True, null=True)  # For media messages
    
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

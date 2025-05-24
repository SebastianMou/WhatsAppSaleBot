from django.contrib import admin
from .models import WhatsAppContact, WhatsAppMessage

@admin.register(WhatsAppContact)
class WhatsAppContactAdmin(admin.ModelAdmin):
    list_display = ('phone_number', 'name', 'last_interaction')
    search_fields = ('phone_number', 'name')
    ordering = ('-last_interaction',)

@admin.register(WhatsAppMessage)
class WhatsAppMessageAdmin(admin.ModelAdmin):
    list_display = ('contact', 'timestamp', 'is_incoming', 'content_summary', 'media_url')
    list_filter = ('is_incoming', 'timestamp')
    search_fields = ('contact__phone_number', 'content')
    ordering = ('-timestamp',)

    def content_summary(self, obj):
        return (obj.content[:75] + '...') if len(obj.content) > 75 else obj.content
    content_summary.short_description = 'Content'


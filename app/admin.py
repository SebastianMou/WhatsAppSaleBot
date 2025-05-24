from django.contrib import admin
from .models import WhatsAppContact, WhatsAppMessage, ClientData

@admin.register(WhatsAppContact)
class WhatsAppContactAdmin(admin.ModelAdmin):
    list_display = ('phone_number', 'name', 'last_interaction', 'message_count')
    search_fields = ('phone_number', 'name')
    ordering = ('-last_interaction',)
    readonly_fields = ('last_interaction',)
    
    def message_count(self, obj):
        return obj.messages.count()
    message_count.short_description = 'Messages'

@admin.register(WhatsAppMessage)
class WhatsAppMessageAdmin(admin.ModelAdmin):
    list_display = ('contact', 'timestamp', 'is_incoming', 'content_summary', 'has_media')
    list_filter = ('is_incoming', 'timestamp')
    search_fields = ('contact__phone_number', 'contact__name', 'content')
    ordering = ('-timestamp',)
    readonly_fields = ('timestamp',)

    def content_summary(self, obj):
        return (obj.content[:75] + '...') if len(obj.content) > 75 else obj.content
    content_summary.short_description = 'Content'
    
    def has_media(self, obj):
        return bool(obj.media_url)
    has_media.boolean = True
    has_media.short_description = 'Media'

@admin.register(ClientData)
class ClientDataAdmin(admin.ModelAdmin):
    list_display = ('fullname', 'email', 'contact_phone', 'curp', 'rfc', 'created_at')
    search_fields = ('fullname', 'email', 'curp', 'rfc', 'contact__phone_number')
    list_filter = ('created_at',)
    ordering = ('-created_at',)
    readonly_fields = ('created_at',)
    
    def contact_phone(self, obj):
        return obj.contact.phone_number
    contact_phone.short_description = 'Phone Number'
    
    fieldsets = (
        ('Contact Information', {
            'fields': ('contact', 'fullname', 'email')
        }),
        ('Government IDs', {
            'fields': ('curp', 'rfc')
        }),
        ('Address & References', {
            'fields': ('address', 'referral_phone_number')
        }),
        ('Timestamps', {
            'fields': ('created_at',),
            'classes': ('collapse',)
        })
    )
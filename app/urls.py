from django.urls import path
from . import views

urlpatterns = [
    # Authentication
    path('register/', views.register_view, name='register'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    
    # WhatsApp Setup
    path('setup-whatsapp/', views.setup_whatsapp_view, name='setup_whatsapp'),
    path('get-qr-code/<str:session_id>/', views.get_qr_code, name='get_qr_code'),
    path('check-whatsapp-status/<str:session_id>/', views.check_whatsapp_status, name='check_whatsapp_status'),
    
    # Dashboard and Chat
    path('', views.whatsapp_dashboard, name='dashboard'),
    path('chat/<int:contact_id>/', views.chat_view, name='chat'),
    
    # Messaging
    path('webhook/receive/', views.webhook_receive_message, name='webhook-receive'),
    path('send-message/', views.send_message, name='send-message'),
]
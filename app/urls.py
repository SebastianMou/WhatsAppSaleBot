from django.urls import path
from . import views

urlpatterns = [
    path('', views.whatsapp_dashboard, name='dashboard'),
    path('chat/<int:contact_id>/', views.chat_view, name='chat'),
    path('webhook/receive/', views.webhook_receive_message, name='webhook-receive'),
    path('send-message/', views.send_message, name='send-message'),
]
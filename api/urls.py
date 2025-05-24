from django.urls import path
from . import views

urlpatterns = [
    path('', views.apiOverview, name='api-overview'),
    # Contact endpoints
    path('contacts/', views.contact_list, name='contact-list'),
    path('contacts/<int:pk>/', views.contact_detail, name='contact-detail'),
    
    # Message endpoints
    path('messages/', views.message_list, name='message-list'),
    path('messages/<int:pk>/', views.message_detail, name='message-detail'),
    
    # Convenience endpoint
    path('contacts/<int:contact_id>/messages/', views.contact_messages, name='contact-messages'),
    
    # AI endpoints - RESTful with ID
    path('contacts/<int:contact_id>/generate-ai-response/', views.generate_ai_response, name='generate-ai-response-by-contact'),
    path('contacts/<int:contact_id>/generate-multiple-ai-responses/', views.generate_multiple_ai_responses, name='generate-multiple-ai-responses-by-contact'),
    
    # AI endpoints - POST body version (ADD THIS LINE)
    path('generate-ai-response/', views.generate_ai_response, name='generate-ai-response'),

    path('client-data/', views.client_data_list, name='client-data-list'),

]
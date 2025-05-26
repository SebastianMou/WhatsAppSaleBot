from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404
from app.models import WhatsAppContact, WhatsAppMessage, ClientData
from .serializers import (
    WhatsAppContactSerializer, 
    WhatsAppMessageSerializer,
    SendMessageSerializer,
    WebhookMessageSerializer,
    ClientDataSerializer  # ADD THIS
)

from app.ai_service import WhatsAppAIService
import json
import logging

@api_view(['GET'])
def apiOverview(request):
    api_urls = {
        # Contact Management URLs
        'All Contacts': '/api/contacts/',
        'Contact Detail': '/api/contacts/<int:pk>/',
        'Contact Create': '/api/contacts/',
        'Contact Update': '/api/contacts/<int:pk>/',
        'Contact Delete': '/api/contacts/<int:pk>/',
        
        # Message Management URLs
        'All Messages': '/api/messages/',
        'Message Detail': '/api/messages/<int:pk>/',
        'Message Create': '/api/messages/',
        'Message Update': '/api/messages/<int:pk>/',
        'Message Delete': '/api/messages/<int:pk>/',
        
        # WhatsApp Specific URLs
        'Messages by Contact': '/api/contacts/<int:contact_id>/messages/',
        'Send Message': '/send-message/',
        'Receive Message Webhook': '/webhook/receive/',
        
        # AI Integration URLs (Two approaches supported)
        'Generate AI Response (POST body)': '/api/generate-ai-response/',
        'Generate AI Response (RESTful)': '/api/contacts/<int:contact_id>/generate-ai-response/',
        'Generate Multiple AI Responses (POST body)': '/api/generate-multiple-ai-responses/',
        'Generate Multiple AI Responses (RESTful)': '/api/contacts/<int:contact_id>/generate-multiple-ai-responses/',
        
        # Dashboard URLs
        'Dashboard Overview': '/',
        'Chat View': '/chat/<int:contact_id>/',
        
        # Testing URLs
        'Test AI with Contact 1': '/api/contacts/1/generate-ai-response/',
        'Test Multiple AI with Contact 1': '/api/contacts/1/generate-multiple-ai-responses/',
    }
    return Response(api_urls)

# Contact Views
@api_view(['GET', 'POST'])
def contact_list(request):
    if request.method == 'GET':
        contacts = WhatsAppContact.objects.all()
        serializer = WhatsAppContactSerializer(contacts, many=True)
        return Response(serializer.data)
    
    elif request.method == 'POST':
        serializer = WhatsAppContactSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@api_view(['GET', 'PUT', 'DELETE'])
def contact_detail(request, pk):
    contact = get_object_or_404(WhatsAppContact, pk=pk)
    
    if request.method == 'GET':
        serializer = WhatsAppContactSerializer(contact)
        return Response(serializer.data)
    
    elif request.method == 'PUT':
        serializer = WhatsAppContactSerializer(contact, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    elif request.method == 'DELETE':
        contact.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

# Message Views
@api_view(['GET', 'POST'])
def message_list(request):
    if request.method == 'GET':
        contact_id = request.query_params.get('contact_id')
        if contact_id:
            messages = WhatsAppMessage.objects.filter(contact_id=contact_id)
        else:
            messages = WhatsAppMessage.objects.all()
        
        serializer = WhatsAppMessageSerializer(messages, many=True)
        return Response(serializer.data)
    
    elif request.method == 'POST':
        serializer = WhatsAppMessageSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@api_view(['GET', 'PUT', 'DELETE'])
def message_detail(request, pk):
    message = get_object_or_404(WhatsAppMessage, pk=pk)
    
    if request.method == 'GET':
        serializer = WhatsAppMessageSerializer(message)
        return Response(serializer.data)
    
    elif request.method == 'PUT':
        serializer = WhatsAppMessageSerializer(message, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    elif request.method == 'DELETE':
        message.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

@api_view(['GET'])
def contact_messages(request, contact_id):
    contact = get_object_or_404(WhatsAppContact, pk=contact_id)
    messages = WhatsAppMessage.objects.filter(contact=contact)
    serializer = WhatsAppMessageSerializer(messages, many=True)
    return Response(serializer.data)

logger = logging.getLogger(__name__)

@api_view(['POST'])
def generate_ai_response(request, contact_id=None):
    """
    Generate AI response for a conversation
    Supports both URL parameter and POST body for contact_id
    """
    try:
        # Get contact_id from URL parameter or POST body
        if contact_id is None:
            data = json.loads(request.body)
            contact_id = data.get('contact_id')
        
        if not contact_id:
            return Response({
                'success': False,
                'error': 'contact_id is required (either in URL or POST body)'
            }, status=400)
        
        logger.info(f"Generating AI response for contact_id: {contact_id}")
        
        # Initialize AI service
        ai_service = WhatsAppAIService()
        
        # Generate response
        result = ai_service.generate_response(contact_id)
        
        if result['success']:
            logger.info(f"AI response generated successfully for contact {contact_id}")
            return Response({
                'success': True,
                'ai_response': result['response'],
                'conversation_length': result.get('conversation_length', 0),
                'contact_id': contact_id
            })
        else:
            logger.error(f"AI service failed for contact {contact_id}: {result['error']}")
            return Response({
                'success': False,
                'error': result['error']
            }, status=500)
            
    except json.JSONDecodeError as e:
        logger.error(f"JSON decode error: {str(e)}")
        return Response({
            'success': False,
            'error': 'Invalid JSON in request body'
        }, status=400)
    except Exception as e:
        logger.error(f"Unexpected error in generate_ai_response: {str(e)}")
        return Response({
            'success': False,
            'error': f'Internal server error: {str(e)}'
        }, status=500)

@api_view(['POST'])
def generate_multiple_ai_responses(request, contact_id=None):
    """
    Generate multiple AI response options
    """
    try:
        # Get contact_id from URL parameter or POST body
        if contact_id is None:
            data = json.loads(request.body)
            contact_id = data.get('contact_id')
            count = data.get('count', 3)
        else:
            data = json.loads(request.body) if request.body else {}
            count = data.get('count', 3)
        
        if not contact_id:
            return Response({
                'success': False,
                'error': 'contact_id is required'
            }, status=400)
        
        logger.info(f"Generating {count} AI responses for contact_id: {contact_id}")
        
        # Initialize AI service
        ai_service = WhatsAppAIService()
        
        # Generate multiple responses
        result = ai_service.generate_multiple_responses(contact_id, count)
        
        result['contact_id'] = contact_id
        return Response(result)
            
    except json.JSONDecodeError as e:
        logger.error(f"JSON decode error: {str(e)}")
        return Response({
            'success': False,
            'error': 'Invalid JSON in request body'
        }, status=400)
    except Exception as e:
        logger.error(f"Unexpected error in generate_multiple_ai_responses: {str(e)}")
        return Response({
            'success': False,
            'error': f'Internal server error: {str(e)}'
        }, status=500)
    
@api_view(['GET', 'POST'])
def client_data_list(request):
    if request.method == 'GET':
        client_data = ClientData.objects.all()
        serializer = ClientDataSerializer(client_data, many=True)
        return Response(serializer.data)
    
    elif request.method == 'POST':
        serializer = ClientDataSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@api_view(['GET', 'PUT', 'DELETE'])
def client_data_detail(request, pk):
    client_data = get_object_or_404(ClientData, pk=pk)
    
    if request.method == 'GET':
        serializer = ClientDataSerializer(client_data)
        return Response(serializer.data)
    
    elif request.method == 'PUT':
        serializer = ClientDataSerializer(client_data, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    elif request.method == 'DELETE':
        client_data.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
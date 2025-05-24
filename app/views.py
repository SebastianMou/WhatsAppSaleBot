# Update your app/views.py file with this enhanced webhook handler

from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.utils import timezone
from datetime import datetime
import json
import requests
from .models import WhatsAppContact, WhatsAppMessage

def whatsapp_dashboard(request):
    """Main dashboard view for WhatsApp messages"""
    contacts = WhatsAppContact.objects.all().order_by('-last_interaction')
    context = {
        'contacts': contacts,
    }
    return render(request, 'app/dashboard.html', context)

def chat_view(request, contact_id):
    """View for displaying chat with a specific contact"""
    try:
        contact = WhatsAppContact.objects.get(pk=contact_id)
        messages = WhatsAppMessage.objects.filter(contact=contact).order_by('timestamp')
        
        context = {
            'contact': contact,
            'messages': messages,
        }
        return render(request, 'app/chat.html', context)
    except WhatsAppContact.DoesNotExist:
        return render(request, 'app/dashboard.html', {
            'error': 'Contact not found'
        })

@csrf_exempt
@require_http_methods(["POST"])
def webhook_receive_message(request):
    """
    Enhanced webhook endpoint for the Baileys service to send messages
    """
    try:
        data = json.loads(request.body)
        print(f"Received webhook data: {data}")  # Debug logging
        
        # Clean phone number
        phone_number = data.get('from', '').replace('+', '').replace(' ', '').replace('-', '')
        if not phone_number.startswith('52'):  # Add Mexico country code if missing
            phone_number = '52' + phone_number
            
        # Get or create contact
        contact, created = WhatsAppContact.objects.get_or_create(
            phone_number=phone_number,
            defaults={'name': data.get('name', '')}
        )
        
        # Update contact name if provided and different
        if data.get('name') and data.get('name') != contact.name:
            contact.name = data.get('name')
            contact.save()
        
        # Parse timestamp
        try:
            if isinstance(data.get('timestamp'), str):
                timestamp = datetime.fromisoformat(data['timestamp'].replace('Z', '+00:00'))
            else:
                timestamp = timezone.now()
        except:
            timestamp = timezone.now()
        
        # Create message (avoid duplicates by checking message_id if provided)
        message_id = data.get('message_id')
        if message_id:
            message, created = WhatsAppMessage.objects.get_or_create(
                contact=contact,
                content=data['content'],
                timestamp=timestamp,
                defaults={
                    'is_incoming': data.get('is_incoming', True),
                    'media_url': data.get('media_url', '')
                }
            )
        else:
            message = WhatsAppMessage.objects.create(
                contact=contact,
                content=data['content'],
                timestamp=timestamp,
                is_incoming=data.get('is_incoming', True),
                media_url=data.get('media_url', '')
            )
        
        # Update contact's last interaction
        contact.last_interaction = timezone.now()
        contact.save()
        
        return JsonResponse({
            'status': 'success',
            'message_id': message.id,
            'contact_created': created if 'created' in locals() else False
        })
        
    except Exception as e:
        print(f"Webhook error: {str(e)}")  # Debug logging
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=400)

@csrf_exempt
@require_http_methods(["POST"])
def send_message(request):
    """
    Send a message through the Baileys service
    Let webhook handle database saving to avoid duplicates
    """
    try:
        data = json.loads(request.body)
        contact_id = data['contact_id']
        message_content = data['content']
        
        contact = WhatsAppContact.objects.get(pk=contact_id)
        
        # Call Baileys service to send the actual message
        baileys_response = requests.post('http://localhost:3001/send-message', 
            json={
                'phone_number': contact.phone_number,
                'message': message_content
            },
            timeout=10
        )
        
        if baileys_response.status_code == 200:
            # DON'T save here - let webhook handle it
            # Just update last interaction
            contact.last_interaction = timezone.now()
            contact.save()
            
            return JsonResponse({
                'status': 'success',
                'message': 'Message sent successfully'
            })
        else:
            return JsonResponse({
                'status': 'error',
                'message': 'Failed to send message via WhatsApp'
            }, status=400)
        
    except WhatsAppContact.DoesNotExist:
        return JsonResponse({
            'status': 'error',
            'message': 'Contact not found'
        }, status=404)
    except requests.exceptions.RequestException:
        return JsonResponse({
            'status': 'error',
            'message': 'WhatsApp service unavailable'
        }, status=503)
    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=400)
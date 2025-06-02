# Update your app/views.py file with this enhanced webhook handler
from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.utils import timezone
from datetime import datetime
import json
import requests
from django.contrib.auth.decorators import login_required
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
import uuid
import qrcode
import io
import base64
from django.shortcuts import redirect
import time
from .models import WhatsAppContact, WhatsAppMessage, WhatsAppSession

def login_view(request):
    if request.method == 'POST':
        username = request.POST['username']
        password = request.POST['password']
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            return redirect('dashboard')
        else:
            return render(request, 'app/login.html', {'error': 'Invalid credentials'})
    return render(request, 'app/login.html')

def logout_view(request):
    logout(request)
    return redirect('login')

def process_message_content(data):
    """Process different types of WhatsApp messages"""
    print(f"Processing message data: {data}")  # Add this debug line
    
    # Handle location messages
    if data.get('type') == 'location' or (data.get('latitude') and data.get('longitude')):
        lat = data.get('latitude')
        lng = data.get('longitude')
        print(f"Location detected: lat={lat}, lng={lng}")  # Add this debug line
        return f"📍 Ubicación compartida: https://www.google.com/maps?q={lat},{lng}"
    
    # Handle regular text messages
    return data.get('content', data.get('text', '[Mensaje sin contenido]'))

def register_view(request):
    if request.method == 'POST':
        username = request.POST['username']
        email = request.POST['email']
        password = request.POST['password']
        password_confirm = request.POST['password_confirm']  # ADD THIS
        
        # Check if passwords match
        if password != password_confirm:
            return render(request, 'app/register.html', {
                'error': 'Passwords do not match'
            })
        
        # Check password length
        if len(password) < 6:
            return render(request, 'app/register.html', {
                'error': 'Password must be at least 6 characters long'
            })
        
        # Check if username exists
        if User.objects.filter(username=username).exists():
            return render(request, 'app/register.html', {
                'error': 'Username already exists'
            })
        
        # Check if email exists
        if User.objects.filter(email=email).exists():
            return render(request, 'app/register.html', {
                'error': 'Email already exists'
            })
        
        # Create user
        user = User.objects.create_user(username=username, email=email, password=password)
        
        # Create a WhatsApp session for this user
        session_id = f"user_{user.id}_{username}"
        session = WhatsAppSession.objects.create(
            session_id=session_id,
            session_name=f"{username}'s WhatsApp",
            user=user,
            is_active=False  # Will be activated when QR is scanned
        )
        
        # Login the user
        login(request, user)
        
        # Redirect to QR setup
        return redirect('setup_whatsapp')
    
    return render(request, 'app/register.html')

@login_required
def setup_whatsapp_view(request):
    """Show QR code for WhatsApp setup"""
    user_session = WhatsAppSession.objects.filter(user=request.user).first()
    
    if not user_session:
        # Create session if doesn't exist
        session_id = f"user_{request.user.id}_{request.user.username}"
        user_session = WhatsAppSession.objects.create(
            session_id=session_id,
            session_name=f"{request.user.username}'s WhatsApp",
            user=request.user,
            is_active=False
        )
    
    context = {
        'session': user_session,
        'session_id': user_session.session_id
    }
    return render(request, 'app/setup_whatsapp.html', context)

@login_required
def get_qr_code(request, session_id):
    """Enhanced API endpoint to get QR code for a session"""
    try:
        # Verify user owns this session
        session = WhatsAppSession.objects.get(session_id=session_id, user=request.user)
        
        # Step 1: Create/initialize session with Baileys if not exists
        print(f"🔍 Initializing session for: {session_id}")
        
        # First create the session
        create_response = requests.post('http://localhost:3001/create-session', 
            json={
                'sessionId': session_id,
                'sessionName': session.session_name
            },
            timeout=15
        )
        
        if create_response.status_code != 200:
            return JsonResponse({
                'success': False,
                'error': f'Failed to create session: {create_response.text}'
            })
        
        # Step 2: Wait a moment for session to initialize
        time.sleep(2)
        
        # Step 3: Get QR code from Baileys
        qr_response = requests.get(f'http://localhost:3001/get-qr/{session_id}', timeout=10)
        
        if qr_response.status_code == 200:
            qr_data = qr_response.json()
            
            if qr_data.get('success'):
                if qr_data.get('connected'):
                    # Already connected
                    session.is_active = True
                    session.phone_number = qr_data.get('phoneNumber', '')
                    session.save()
                    
                    return JsonResponse({
                        'success': True,
                        'connected': True,
                        'phone_number': qr_data.get('phoneNumber', '')
                    })
                
                elif qr_data.get('qrCode'):
                    # QR code available
                    return JsonResponse({
                        'success': True,
                        'qr_code': qr_data['qrCode'],  # Base64 data URL
                        'waiting': False
                    })
                
                elif qr_data.get('waiting'):
                    # Still waiting for QR
                    return JsonResponse({
                        'success': True,
                        'waiting': True,
                        'message': 'Waiting for QR code...'
                    })
            
            return JsonResponse({
                'success': False,
                'error': qr_data.get('error', 'Unknown error from Baileys')
            })
        
        else:
            return JsonResponse({
                'success': False,
                'error': f'Baileys service error: {qr_response.status_code}'
            })
            
    except WhatsAppSession.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Session not found'
        })
    except requests.exceptions.RequestException as e:
        return JsonResponse({
            'success': False,
            'error': f'Connection error: {str(e)}'
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        })

@login_required
def check_whatsapp_status(request, session_id):
    """Check if WhatsApp is connected"""
    try:
        session = WhatsAppSession.objects.get(session_id=session_id, user=request.user)
        
        # Check status with Baileys service
        response = requests.get(f'http://localhost:3001/sessions', timeout=10)
        
        if response.status_code == 200:
            sessions_data = response.json()
            for bot_session in sessions_data.get('sessions', []):
                if bot_session['sessionId'] == session_id:
                    if bot_session['isConnected']:
                        # Update database
                        session.is_active = True
                        session.phone_number = bot_session.get('phoneNumber', '')
                        session.save()
                        
                        return JsonResponse({
                            'success': True,
                            'connected': True,
                            'phone_number': bot_session.get('phoneNumber', '')
                        })
        
        return JsonResponse({
            'success': True,
            'connected': False
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        })

@login_required
def whatsapp_dashboard(request):
    # Get only sessions for the logged-in user
    user_sessions = WhatsAppSession.objects.filter(user=request.user)
    contacts = WhatsAppContact.objects.filter(session__in=user_sessions).order_by('-last_interaction')
    
    print(f"🔍 USER: {request.user}")
    print(f"🔍 USER SESSIONS: {[s.session_id for s in user_sessions]}")
    print(f"🔍 USER CONTACTS: {contacts.count()}")
    
    context = {
        'contacts': contacts,
        'sessions': user_sessions,
    }
    return render(request, 'app/dashboard.html', context)

@login_required
def chat_view(request, contact_id):
    try:
        # Ensure contact belongs to user's sessions
        user_sessions = WhatsAppSession.objects.filter(user=request.user)
        contact = WhatsAppContact.objects.get(pk=contact_id, session__in=user_sessions)
        messages = WhatsAppMessage.objects.filter(contact=contact).order_by('timestamp')
        
        context = {
            'contact': contact,
            'messages': messages,
        }
        return render(request, 'app/chat.html', context)
    except WhatsAppContact.DoesNotExist:
        return render(request, 'app/dashboard.html', {
            'error': 'Contact not found or you do not have access to this contact'
        })

@csrf_exempt
@require_http_methods(["POST"])
def webhook_receive_message(request):
    try:
        data = json.loads(request.body)
        print(f"🔍 FULL WEBHOOK DATA: {json.dumps(data, indent=2)}")
        
        session_id = data.get('session_id')
        print(f"🔍 SESSION_ID RECEIVED: '{session_id}'")
        
        if not session_id:
            print("❌ NO SESSION_ID PROVIDED")
            return JsonResponse({'status': 'error', 'message': 'session_id required'}, status=400)
        
        # Get session
        try:
            whatsapp_session = WhatsAppSession.objects.get(session_id=session_id)
            print(f"✅ FOUND SESSION: {whatsapp_session}")
        except WhatsAppSession.DoesNotExist:
            print(f"❌ SESSION NOT FOUND: '{session_id}'")
            available_sessions = WhatsAppSession.objects.all()
            print(f"🔍 AVAILABLE SESSIONS: {[s.session_id for s in available_sessions]}")
            return JsonResponse({'status': 'error', 'message': 'Invalid session_id'}, status=400)
        
        # Clean phone number
        phone_number = data.get('from', '').replace('+', '').replace(' ', '').replace('-', '')
        if not phone_number.startswith('52'):
            phone_number = '52' + phone_number
        print(f"🔍 CLEANED PHONE NUMBER: '{phone_number}'")
            
        # Create/get contact
        try:
            contact, created = WhatsAppContact.objects.get_or_create(
                phone_number=phone_number,
                session=whatsapp_session,
                defaults={'name': data.get('name', '')}
            )
            print(f"✅ CONTACT: {contact} (created: {created})")
        except Exception as e:
            print(f"❌ ERROR CREATING CONTACT: {str(e)}")
            return JsonResponse({'status': 'error', 'message': f'Contact creation failed: {str(e)}'}, status=400)
        
        # Update contact name if provided
        if data.get('name') and not contact.name:
            contact.name = data.get('name')
            contact.save()
            print(f"✅ UPDATED CONTACT NAME: {contact.name}")

        # Parse timestamp
        try:
            if isinstance(data.get('timestamp'), str):
                timestamp = datetime.fromisoformat(data['timestamp'].replace('Z', '+00:00'))
            else:
                timestamp = timezone.now()
            print(f"✅ TIMESTAMP: {timestamp}")
        except Exception as e:
            print(f"❌ TIMESTAMP ERROR: {str(e)}")
            timestamp = timezone.now()
        
        # Create message
        try:
            message_content = process_message_content(data)
            print(f"✅ MESSAGE CONTENT: '{message_content}'")
            
            message_id = data.get('message_id')
            if message_id:
                message, msg_created = WhatsAppMessage.objects.get_or_create(
                    contact=contact,
                    content=message_content,
                    timestamp=timestamp,
                    defaults={
                        'is_incoming': data.get('is_incoming', True),
                        'media_url': data.get('media_url', '')
                    }
                )
            else:
                message = WhatsAppMessage.objects.create(
                    contact=contact,
                    content=message_content,
                    timestamp=timestamp,
                    is_incoming=data.get('is_incoming', True),
                    media_url=data.get('media_url', '')
                )
                msg_created = True
            
            print(f"✅ MESSAGE CREATED: {message} (created: {msg_created})")
        except Exception as e:
            print(f"❌ ERROR CREATING MESSAGE: {str(e)}")
            return JsonResponse({'status': 'error', 'message': f'Message creation failed: {str(e)}'}, status=400)
        
        # Update contact's last interaction
        try:
            contact.last_interaction = timezone.now()
            contact.save()
            print(f"✅ UPDATED LAST INTERACTION")
        except Exception as e:
            print(f"❌ ERROR UPDATING LAST INTERACTION: {str(e)}")
        
        print(f"✅ WEBHOOK SUCCESS - RETURNING 200")
        return JsonResponse({
            'status': 'success',
            'message_id': message.id,
            'contact_created': created
        })
        
    except Exception as e:
        print(f"❌ WEBHOOK ERROR: {str(e)}")
        import traceback
        print(f"❌ FULL TRACEBACK: {traceback.format_exc()}")
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=400)
    
@csrf_exempt
@require_http_methods(["POST"])
def send_message(request):
    """
    Send a message through the Baileys service
    """
    try:
        data = json.loads(request.body)
        contact_id = data['contact_id']
        message_content = data['content']
        
        # Get the contact and its session
        contact = WhatsAppContact.objects.get(pk=contact_id)
        session_id = contact.session.session_id  # Get the session_id from the contact
        
        print(f"🔍 SENDING MESSAGE:")
        print(f"   Contact: {contact}")
        print(f"   Session ID: {session_id}")
        print(f"   Phone: {contact.phone_number}")
        print(f"   Message: {message_content}")
        
        # Call Baileys service with sessionId
        baileys_response = requests.post('http://localhost:3001/send-message', 
            json={
                'sessionId': session_id,  # ADD THIS - required by your WhatsApp bot
                'phone_number': contact.phone_number,
                'message': message_content
            },
            timeout=10
        )
        
        print(f"🔍 BAILEYS RESPONSE: {baileys_response.status_code}")
        print(f"🔍 BAILEYS RESPONSE DATA: {baileys_response.text}")
        
        if baileys_response.status_code == 200:
            # Update last interaction
            contact.last_interaction = timezone.now()
            contact.save()
            
            return JsonResponse({
                'status': 'success',
                'message': 'Message sent successfully'
            })
        else:
            return JsonResponse({
                'status': 'error',
                'message': f'Failed to send message via WhatsApp: {baileys_response.text}'
            }, status=400)
        
    except WhatsAppContact.DoesNotExist:
        return JsonResponse({
            'status': 'error',
            'message': 'Contact not found'
        }, status=404)
    except requests.exceptions.RequestException as e:
        print(f"❌ REQUEST ERROR: {str(e)}")
        return JsonResponse({
            'status': 'error',
            'message': 'WhatsApp service unavailable'
        }, status=503)
    except Exception as e:
        print(f"❌ SEND MESSAGE ERROR: {str(e)}")
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=400)
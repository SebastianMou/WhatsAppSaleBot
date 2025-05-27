const { 
    default: makeWASocket, 
    DisconnectReason, 
    useMultiFileAuthState,
    fetchLatestBaileysVersion 
} = require('@whiskeysockets/baileys');
const qrcode = require('qrcode-terminal');
const axios = require('axios');
const fs = require('fs');
const path = require('path');

// Django API configuration
const DJANGO_API_BASE = 'http://localhost:7000';
const WEBHOOK_RECEIVE_URL = `${DJANGO_API_BASE}/webhook/receive/`;
const CONTACTS_API_URL = `${DJANGO_API_BASE}/api/contacts/`;

class WhatsAppBot {
    constructor() {
        this.sock = null;
        this.isConnected = false;
        this.chats = new Map(); // Store chats locally
    }

    async start() {
        try {
            const { state, saveCreds } = await useMultiFileAuthState('auth_info_baileys');
            const { version, isLatest } = await fetchLatestBaileysVersion();
            
            console.log(`Using WA v${version.join('.')}, isLatest: ${isLatest}`);

            this.sock = makeWASocket({
                version,
                auth: state,
                printQRInTerminal: true,
                browser: ['WhatsApp Business Bot', 'Chrome', '10.0.0'],
            });

            // Handle connection updates
            this.sock.ev.on('connection.update', async (update) => {
                const { connection, lastDisconnect, qr } = update;
                
                if (qr) {
                    console.log('\n📱 Scan this QR code with your WhatsApp Business app:');
                    qrcode.generate(qr, { small: true });
                    console.log('\n⚠️  Make sure to scan with WhatsApp Business on: 72 7441286312');
                }

                if (connection === 'close') {
                    const shouldReconnect = (lastDisconnect?.error)?.output?.statusCode !== DisconnectReason.loggedOut;
                    console.log('Connection closed due to:', lastDisconnect?.error, ', reconnecting:', shouldReconnect);
                    
                    if (shouldReconnect) {
                        this.start();
                    }
                    this.isConnected = false;
                } else if (connection === 'open') {
                    console.log('✅ Connected to WhatsApp Business!');
                    this.isConnected = true;
                    
                    // Start syncing process
                    console.log('🔄 Starting to sync WhatsApp data...');
                    // Wait a bit for the connection to stabilize
                    setTimeout(() => this.syncExistingData(), 3000);
                }
            });

            // Save credentials when updated
            this.sock.ev.on('creds.update', saveCreds);

            // Handle chats update - This is how we get chat list in current Baileys
            this.sock.ev.on('chats.set', async (chatSet) => {
                console.log(`📋 Got ${chatSet.chats.length} chats from WhatsApp`);
                
                // Store chats locally
                for (const chat of chatSet.chats) {
                    this.chats.set(chat.id, chat);
                }
                
                // Sync the chats to Django
                await this.processChatList(chatSet.chats);
            });

            // Handle chat updates
            this.sock.ev.on('chats.update', (chatUpdates) => {
                for (const update of chatUpdates) {
                    if (this.chats.has(update.id)) {
                        // Update existing chat info
                        const existingChat = this.chats.get(update.id);
                        this.chats.set(update.id, { ...existingChat, ...update });
                    }
                }
            });

            // Handle incoming messages
            this.sock.ev.on('messages.upsert', async (m) => {
                const messages = m.messages;
                
                for (const msg of messages) {
                    if (msg.message) {
                        await this.handleMessage(msg);
                    }
                }
            });

            // Handle message updates (read receipts, etc.)
            this.sock.ev.on('messages.update', (messageUpdate) => {
                console.log('Message update:', messageUpdate);
            });

        } catch (error) {
            console.error('Error starting WhatsApp bot:', error);
            setTimeout(() => this.start(), 5000);
        }
    }

    async processChatList(chats) {
        console.log('🔄 Processing chat list...');
        
        for (const chat of chats.slice(0, 20)) { // Process first 20 chats
            if (chat.id.endsWith('@s.whatsapp.net')) { // Individual chats only
                await this.processSingleChat(chat);
            }
        }
        
        console.log('✅ Chat processing completed!');
    }

    async processSingleChat(chat) {
        try {
            const phoneNumber = chat.id.replace('@s.whatsapp.net', '');
            const contactName = chat.name || '';

            console.log(`📞 Processing contact: ${contactName || phoneNumber}`);

            // Create/update contact in Django
            const contactData = {
                phone_number: phoneNumber,
                name: contactName
            };

            await this.sendToDjango(CONTACTS_API_URL, contactData);

            // Try to get recent messages for this chat
            try {
                const messages = await this.sock.fetchMessagesFromWA(chat.id, 20);
                
                for (const msg of messages) {
                    if (msg.message) {
                        await this.handleMessage(msg, phoneNumber, contactName);
                    }
                }
            } catch (msgError) {
                console.log(`⚠️  Could not fetch messages for ${phoneNumber}:`, msgError.message);
                // This is OK, we'll get messages as they come in
            }

        } catch (error) {
            console.error(`Error processing chat ${chat.id}:`, error);
        }
    }

    async handleMessage(msg, phoneNumber = null, contactName = null) {
        try {
            const messageContent = this.extractMessageContent(msg);
            const isLocationMessage = typeof messageContent === 'object' && messageContent.type === 'location';
            const senderNumber = phoneNumber || msg.key.remoteJid?.replace('@s.whatsapp.net', '');
            const isIncoming = !msg.key.fromMe;
            
            if ((!messageContent && !isLocationMessage) || !senderNumber) return;

            const displayContent = isLocationMessage ? '[Location Shared]' : messageContent;
            console.log(`${isIncoming ? '📨' : '📤'} Message ${isIncoming ? 'from' : 'to'} ${senderNumber}: ${displayContent.substring(0, 50)}...`);
            
            // Send to Django webhook
            const messageData = {
                from: senderNumber,
                content: isLocationMessage ? '' : messageContent,
                timestamp: new Date(msg.messageTimestamp * 1000).toISOString(),
                message_id: msg.key.id,
                name: contactName || msg.pushName || '',
                is_incoming: isIncoming,
                ...(isLocationMessage && {
                    type: 'location',
                    latitude: messageContent.latitude,
                    longitude: messageContent.longitude
                })
            };

            await this.sendToDjango(WEBHOOK_RECEIVE_URL, messageData);

        } catch (error) {
            console.error('Error handling message:', error);
        }
    }

    async handleIncomingMessage(msg) {
        // This method is now replaced by handleMessage
        await this.handleMessage(msg);
    }

    extractMessageContent(msg) {
        if (msg.message?.conversation) {
            return msg.message.conversation;
        }
        if (msg.message?.extendedTextMessage?.text) {
            return msg.message.extendedTextMessage.text;
        }
        if (msg.message?.imageMessage?.caption) {
            return `[Image] ${msg.message.imageMessage.caption}`;
        }
        if (msg.message?.videoMessage?.caption) {
            return `[Video] ${msg.message.videoMessage.caption}`;
        }
        if (msg.message?.documentMessage?.caption) {
            return `[Document] ${msg.message.documentMessage.caption}`;
        }
        if (msg.message?.imageMessage) {
            return '[Image]';
        }
        if (msg.message?.videoMessage) {
            return '[Video]';
        }
        if (msg.message?.documentMessage) {
            return '[Document]';
        }
        if (msg.message?.locationMessage) {
            return {
                content: '',
                type: 'location',
                latitude: msg.message.locationMessage.degreesLatitude,
                longitude: msg.message.locationMessage.degreesLongitude
            };
        }
        return null;
    }

    async syncExistingData() {
        try {
            console.log('🔄 Starting to sync existing WhatsApp data...');
            
            // In current Baileys, we wait for the chats.set event
            // which will automatically trigger our chat processing
            console.log('⏳ Waiting for WhatsApp to send chat data...');
            
            // If we have chats stored locally, process them
            if (this.chats.size > 0) {
                await this.processChatList(Array.from(this.chats.values()));
            }

        } catch (error) {
            console.error('Error syncing existing data:', error);
        }
    }

    async sendMessage(phoneNumber, message) {
        try {
            if (!this.isConnected) {
                throw new Error('WhatsApp not connected');
            }

            const jid = phoneNumber + '@s.whatsapp.net';
            await this.sock.sendMessage(jid, { text: message });
            
            console.log(`✅ Message sent to ${phoneNumber}: ${message}`);
            return { success: true };
        } catch (error) {
            console.error('Error sending message:', error);
            return { success: false, error: error.message };
        }
    }

    async sendToDjango(url, data) {
        try {
            console.log(`🔗 Sending to Django: ${url}`, { 
                phone_number: data.phone_number || data.from, 
                content: data.content?.substring(0, 50) || 'contact data'
            });
            
            const response = await axios.post(url, data, {
                headers: {
                    'Content-Type': 'application/json',
                },
                timeout: 10000
            });
            
            console.log(`✅ Django response: ${response.status}`);
            return response.data;
        } catch (error) {
            if (error.code === 'ECONNREFUSED') {
                console.log('⚠️  Django server not running, skipping data sync');
            } else {
                console.error('❌ Error sending to Django:', error.message);
                if (error.response?.data) {
                    console.error('Django error details:', error.response.data);
                }
            }
        }
    }
}

// Express server for Django to send messages
const express = require('express');
const cors = require('cors');
const app = express();
const port = 3001;

app.use(cors());
app.use(express.json());

let whatsappBot = null;

// Endpoint for Django to send messages
app.post('/send-message', async (req, res) => {
    try {
        const { phone_number, message } = req.body;
        
        if (!whatsappBot || !whatsappBot.isConnected) {
            return res.status(503).json({ 
                success: false, 
                error: 'WhatsApp not connected' 
            });
        }

        const result = await whatsappBot.sendMessage(phone_number, message);
        res.json(result);
    } catch (error) {
        res.status(500).json({ 
            success: false, 
            error: error.message 
        });
    }
});

// Health check endpoint
app.get('/health', (req, res) => {
    res.json({ 
        status: 'running',
        connected: whatsappBot?.isConnected || false,
        chats_loaded: whatsappBot?.chats?.size || 0
    });
});

// Manual sync trigger endpoint
app.post('/sync', async (req, res) => {
    try {
        if (!whatsappBot || !whatsappBot.isConnected) {
            return res.status(503).json({ 
                success: false, 
                error: 'WhatsApp not connected' 
            });
        }

        await whatsappBot.syncExistingData();
        res.json({ success: true, message: 'Sync triggered' });
    } catch (error) {
        res.status(500).json({ 
            success: false, 
            error: error.message 
        });
    }
});

// Start the bot and server
async function main() {
    console.log('🚀 Starting WhatsApp Business Bot...');
    console.log('📞 Target number: 72 7441286312');
    
    // Start Express server
    app.listen(port, () => {
        console.log(`🌐 Express server running on http://localhost:${port}`);
        console.log(`🔧 Health check: http://localhost:${port}/health`);
        console.log(`🔄 Manual sync: POST http://localhost:${port}/sync`);
    });

    // Start WhatsApp bot
    whatsappBot = new WhatsAppBot();
    await whatsappBot.start();
}

main().catch(console.error);
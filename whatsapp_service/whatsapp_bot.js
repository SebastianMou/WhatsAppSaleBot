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
const express = require('express');
const cors = require('cors');
const QRCode = require('qrcode');

// Django API configuration
const DJANGO_API_BASE = 'http://localhost:7000';
const WEBHOOK_RECEIVE_URL = `${DJANGO_API_BASE}/webhook/receive/`;
const CONTACTS_API_URL = `${DJANGO_API_BASE}/api/contacts/`;

class WhatsAppSession {
    constructor(sessionId, sessionName) {
        this.sessionId = sessionId;
        this.sessionName = sessionName;
        this.sock = null;
        this.isConnected = false;
        this.chats = new Map();
        this.authDir = `auth_info_baileys_${sessionId}`;
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 5;
        this.currentQR = null; // ADD THIS - store current QR for web display
        
        console.log(`📱 Creating session: ${sessionName} (ID: ${sessionId})`);
    }


    async start() {
        try {
            // Create auth directory if it doesn't exist
            if (!fs.existsSync(this.authDir)) {
                fs.mkdirSync(this.authDir, { recursive: true });
                console.log(`📁 Created auth directory: ${this.authDir}`);
            }

            const { state, saveCreds } = await useMultiFileAuthState(this.authDir);
            const { version, isLatest } = await fetchLatestBaileysVersion();
            
            console.log(`🔧 Session ${this.sessionName}: Using WA v${version.join('.')}, isLatest: ${isLatest}`);

            this.sock = makeWASocket({
                version,
                auth: state,
                printQRInTerminal: false, // We'll handle QR display manually
                browser: [`WhatsApp Business Bot - ${this.sessionName}`, 'Chrome', '10.0.0'],
            });

            // Handle connection updates
            this.sock.ev.on('connection.update', async (update) => {
                const { connection, lastDisconnect, qr } = update;
                
                if (qr) {
                    this.currentQR = qr; // STORE QR for web access
                    console.log(`\n📱 QR CODE FOR SESSION: ${this.sessionName} (${this.sessionId})`);
                    console.log('=' * 60);
                    qrcode.generate(qr, { small: true });
                    console.log(`\n⚠️  Scan this QR with WhatsApp Business for: ${this.sessionName}`);
                    console.log('=' * 60);
                }

                if (connection === 'close') {
                    this.currentQR = null
                    const statusCode = lastDisconnect?.error?.output?.statusCode;
                    const shouldReconnect = statusCode !== DisconnectReason.loggedOut;
                    
                    console.log(`🔌 Session ${this.sessionName} closed: ${statusCode}, reconnecting: ${shouldReconnect}`);
                    
                    // STOP RECONNECTION if max attempts reached
                    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
                        console.log(`❌ Session ${this.sessionName} max reconnect attempts reached. STOPPED.`);
                        this.isConnected = false;
                        return; // STOP HERE - don't reconnect
                    }
                    
                    // Only reconnect for specific errors, not QR timeout (408)
                    if (shouldReconnect && statusCode !== 408) {
                        this.reconnectAttempts++;
                        console.log(`🔄 Session ${this.sessionName} reconnect attempt ${this.reconnectAttempts}/${this.maxReconnectAttempts}`);
                        setTimeout(() => this.start(), 30000);
                    } else {
                        console.log(`🛑 Session ${this.sessionName} - QR timeout or logged out. Stopping reconnection.`);
                    }
                    this.isConnected = false;
                    
                } else if (connection === 'open') {
                    this.currentQR = null;
                    console.log(`✅ Session ${this.sessionName} connected to WhatsApp Business!`);
                    this.isConnected = true;
                    this.reconnectAttempts = 0;

                    const sessionInfo = this.sock.user;
                    console.log(`📞 Session ${this.sessionName} number: ${sessionInfo?.id || 'Unknown'}`);
                    
                    setTimeout(() => this.syncExistingData(), 3000);
                }
            });

            // Save credentials when updated
            this.sock.ev.on('creds.update', saveCreds);

            // Handle chats update
            this.sock.ev.on('chats.set', async (chatSet) => {
                console.log(`📋 Session ${this.sessionName}: Got ${chatSet.chats.length} chats`);
                
                for (const chat of chatSet.chats) {
                    this.chats.set(chat.id, chat);
                }
                
                await this.processChatList(chatSet.chats);
            });

            // Handle chat updates
            this.sock.ev.on('chats.update', (chatUpdates) => {
                for (const update of chatUpdates) {
                    if (this.chats.has(update.id)) {
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

        } catch (error) {
            console.error(`❌ Error starting session ${this.sessionName}:`, error);
            
            // STOP if max attempts reached
            if (this.reconnectAttempts >= this.maxReconnectAttempts) {
                console.log(`❌ Session ${this.sessionName} max startup attempts reached. STOPPED.`);
                return;
            }
            
            this.reconnectAttempts++;
            console.log(`🔄 Session ${this.sessionName} startup retry ${this.reconnectAttempts}/${this.maxReconnectAttempts}`);
            setTimeout(() => this.start(), 60000); // Wait 60 seconds for startup errors
        }

    }

    async processChatList(chats) {
        console.log(`🔄 Processing chat list for session: ${this.sessionName}...`);
        
        for (const chat of chats.slice(0, 20)) {
            if (chat.id.endsWith('@s.whatsapp.net')) {
                await this.processSingleChat(chat);
            }
        }
        
        console.log(`✅ Chat processing completed for session: ${this.sessionName}!`);
    }

    async processSingleChat(chat) {
        try {
            const phoneNumber = chat.id.replace('@s.whatsapp.net', '');
            const contactName = chat.name || '';

            console.log(`📞 Session ${this.sessionName} - Processing contact: ${contactName || phoneNumber}`);

            const contactData = {
                phone_number: phoneNumber,
                name: contactName,
                session_id: this.sessionId // CHANGE: Use sessionId instead of sessionName
            };

            await this.sendToDjango(CONTACTS_API_URL, contactData);

            try {
                const messages = await this.sock.fetchMessagesFromWA(chat.id, 20);
                
                for (const msg of messages) {
                    if (msg.message) {
                        await this.handleMessage(msg, phoneNumber, contactName);
                    }
                }
            } catch (msgError) {
                console.log(`⚠️  Session ${this.sessionName} - Could not fetch messages for ${phoneNumber}:`, msgError.message);
            }

        } catch (error) {
            console.error(`❌ Session ${this.sessionName} - Error processing chat ${chat.id}:`, error);
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
            console.log(`${isIncoming ? '📨' : '📤'} Session ${this.sessionName} - Message ${isIncoming ? 'from' : 'to'} ${senderNumber}: ${displayContent.substring(0, 50)}...`);
            
            const messageData = {
                from: senderNumber,
                content: isLocationMessage ? '' : messageContent,
                timestamp: new Date(msg.messageTimestamp * 1000).toISOString(),
                message_id: msg.key.id,
                name: contactName || msg.pushName || '',
                is_incoming: isIncoming,
                session_id: this.sessionId, // CHANGE: Use sessionId instead of sessionName
                // session_name: this.sessionName,  // Remove this or keep as additional info
                ...(isLocationMessage && {
                    type: 'location',
                    latitude: messageContent.latitude,
                    longitude: messageContent.longitude
                })
            };

            await this.sendToDjango(WEBHOOK_RECEIVE_URL, messageData);

        } catch (error) {
            console.error(`❌ Session ${this.sessionName} - Error handling message:`, error);
        }
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
            console.log(`🔄 Starting to sync existing data for session: ${this.sessionName}...`);
            
            if (this.chats.size > 0) {
                await this.processChatList(Array.from(this.chats.values()));
            }

        } catch (error) {
            console.error(`❌ Session ${this.sessionName} - Error syncing existing data:`, error);
        }
    }

    async sendMessage(phoneNumber, message) {
        try {
            if (!this.isConnected) {
                throw new Error(`WhatsApp session ${this.sessionName} not connected`);
            }

            const jid = phoneNumber + '@s.whatsapp.net';
            await this.sock.sendMessage(jid, { text: message });
            
            console.log(`✅ Session ${this.sessionName} - Message sent to ${phoneNumber}: ${message}`);
            return { success: true, session: this.sessionName };
        } catch (error) {
            console.error(`❌ Session ${this.sessionName} - Error sending message:`, error);
            return { success: false, error: error.message, session: this.sessionName };
        }
    }

    async sendToDjango(url, data) {
        try {
            console.log(`🔗 Session ${this.sessionName} - Sending to Django: ${url}`);
            console.log(`🔍 ACTUAL DATA BEING SENT:`, JSON.stringify(data, null, 2)); // Show real data
            
            const response = await axios.post(url, data, {
                headers: {
                    'Content-Type': 'application/json',
                },
                timeout: 10000
            });
            
            console.log(`✅ Session ${this.sessionName} - Django response: ${response.status}`);
            return response.data;
        } catch (error) {
            if (error.code === 'ECONNREFUSED') {
                console.log(`⚠️  Session ${this.sessionName} - Django server not running, skipping data sync`);
            } else {
                console.error(`❌ Session ${this.sessionName} - Error sending to Django:`, error.message);
                console.error(`❌ Error response:`, error.response?.data); // Show Django error details
            }
        }
    }

    getStatus() {
        return {
            sessionId: this.sessionId,
            sessionName: this.sessionName,
            isConnected: this.isConnected,
            chatsLoaded: this.chats.size,
            phoneNumber: this.sock?.user?.id || 'Not connected'
        };
    }
}

class MultiSessionManager {
    constructor() {
        this.sessions = new Map();
    }

    createSession(sessionId, sessionName) {
        if (this.sessions.has(sessionId)) {
            console.log(`⚠️  Session ${sessionId} already exists`);
            return this.sessions.get(sessionId);
        }

        const session = new WhatsAppSession(sessionId, sessionName);
        this.sessions.set(sessionId, session);
        console.log(`✅ Created session: ${sessionName} (${sessionId})`);
        return session;
    }

    async startSession(sessionId) {
        const session = this.sessions.get(sessionId);
        if (!session) {
            throw new Error(`Session ${sessionId} not found`);
        }

        await session.start();
        return session;
    }

    async startAllSessions() {
        const promises = [];
        for (const [sessionId, session] of this.sessions) {
            promises.push(session.start());
        }
        await Promise.all(promises);
    }

    getSession(sessionId) {
        return this.sessions.get(sessionId);
    }

    getAllSessions() {
        return Array.from(this.sessions.values()).map(session => session.getStatus());
    }

    async sendMessage(sessionId, phoneNumber, message) {
        const session = this.sessions.get(sessionId);
        if (!session) {
            return { success: false, error: `Session ${sessionId} not found` };
        }

        return await session.sendMessage(phoneNumber, message);
    }
}

// Initialize the multi-session manager
const sessionManager = new MultiSessionManager();

// Create Express server
const app = express();
const port = 3001;

app.use(cors());
app.use(express.json());

// Endpoint to create a new session
app.post('/create-session', async (req, res) => {
    try {
        const { sessionId, sessionName } = req.body;
        
        if (!sessionId || !sessionName) {
            return res.status(400).json({ 
                success: false, 
                error: 'sessionId and sessionName are required' 
            });
        }

        const session = sessionManager.createSession(sessionId, sessionName);
        await sessionManager.startSession(sessionId);
        
        res.json({ 
            success: true, 
            message: `Session ${sessionName} created and started`,
            session: session.getStatus()
        });
    } catch (error) {
        res.status(500).json({ 
            success: false, 
            error: error.message 
        });
    }
});

// Endpoint to send message from specific session
app.post('/send-message', async (req, res) => {
    try {
        const { sessionId, phone_number, message } = req.body;
        
        if (!sessionId) {
            return res.status(400).json({ 
                success: false, 
                error: 'sessionId is required' 
            });
        }

        const result = await sessionManager.sendMessage(sessionId, phone_number, message);
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
    const sessions = sessionManager.getAllSessions();
    res.json({ 
        status: 'running',
        totalSessions: sessions.length,
        sessions: sessions
    });
});

// Get all sessions status
app.get('/sessions', (req, res) => {
    const sessions = sessionManager.getAllSessions();
    res.json({ 
        success: true,
        sessions: sessions
    });
});

// Manual sync trigger for specific session
app.post('/sync', async (req, res) => {
    try {
        const { sessionId } = req.body;
        
        if (!sessionId) {
            return res.status(400).json({ 
                success: false, 
                error: 'sessionId is required' 
            });
        }

        const session = sessionManager.getSession(sessionId);
        if (!session || !session.isConnected) {
            return res.status(503).json({ 
                success: false, 
                error: `Session ${sessionId} not connected` 
            });
        }

        await session.syncExistingData();
        res.json({ success: true, message: `Sync triggered for session ${sessionId}` });
    } catch (error) {
        res.status(500).json({ 
            success: false, 
            error: error.message 
        });
    }
});

// Start the server and default sessions
// Move this INSIDE the main() function, after app.listen():
async function main() {
    console.log('🚀 Starting Multi-Session WhatsApp Business Bot...');
    
    // Start Express server
    app.listen(port, () => {
        console.log(`🌐 Express server running on http://localhost:${port}`);
        console.log(`🔧 Health check: http://localhost:${port}/health`);
        console.log(`📱 Sessions status: http://localhost:${port}/sessions`);
        console.log(`➕ Create session: POST http://localhost:${port}/create-session`);
        console.log(`💬 Send message: POST http://localhost:${port}/send-message`);
        console.log(`📱 Get QR code: GET http://localhost:${port}/get-qr/:sessionId`); // ADD THIS LINE
    });

    console.log('\n✅ WhatsApp Bot Server ready! Sessions will be created on-demand via API.');
}

app.get('/get-qr/:sessionId', (req, res) => {
    const { sessionId } = req.params;
    console.log(`🔍 QR request for session: ${sessionId}`);
    
    const session = sessionManager.getSession(sessionId);
    
    if (!session) {
        console.log(`❌ Session not found: ${sessionId}`);
        return res.status(404).json({ 
            success: false, 
            error: 'Session not found' 
        });
    }
    
    console.log(`🔍 Session status: connected=${session.isConnected}, hasQR=${!!session.currentQR}`);
    
    if (session.currentQR) {
        console.log(`📱 Generating QR image for session: ${sessionId}`);
        // Generate QR as base64 image for web display
        QRCode.toDataURL(session.currentQR)
            .then(url => {
                console.log(`✅ QR image generated successfully for: ${sessionId}`);
                res.json({
                    success: true,
                    qrCode: url, // Base64 data URL
                    sessionName: session.sessionName
                });
            })
            .catch(err => {
                console.error(`❌ QR generation error for ${sessionId}:`, err);
                res.status(500).json({
                    success: false,
                    error: 'Failed to generate QR image'
                });
            });
    } else if (session.isConnected) {
        console.log(`✅ Session already connected: ${sessionId}`);
        res.json({
            success: true,
            connected: true,
            phoneNumber: session.sock?.user?.id
        });
    } else {
        console.log(`⏳ Waiting for QR code for session: ${sessionId}`);
        res.json({
            success: true,
            waiting: true,
            message: 'Waiting for QR code...'
        });
    }
});

main().catch(console.error);

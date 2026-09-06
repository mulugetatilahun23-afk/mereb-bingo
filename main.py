from flask import Flask, request, jsonify, render_template_string
import sqlite3
import os
import random
import json
import re
import urllib.parse

app = Flask(__name__)

# Environment Variables (ለ GitHub ደህንነት ሲባል ከ env ይወሰዳሉ)
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
BOT_USERNAME = os.environ.get("BOT_USERNAME", "MerebBingoBot")
DB_NAME = 'mereb_bingo.db'

# የክፍያ ተቀባይ መረጃዎች
MERCHANT_PHONE = "0923410403"
MERCHANT_NAME = "MULUGETA TILAHUN"
REFERRAL_BONUS = 5.0

def get_db():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()
    
    # 1. የተጫዋቾች ሰንጠረዥ
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            telegram_id INTEGER PRIMARY KEY, 
            first_name TEXT,
            phone_number TEXT, 
            balance REAL DEFAULT 0.0, 
            commission_balance REAL DEFAULT 0.0,
            agent_id INTEGER
        )
    ''')
    
    # 2. የክፍያዎች ሰንጠረዥ
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER,
            tx_id TEXT UNIQUE,
            amount REAL,
            type TEXT,
            method TEXT,
            status TEXT DEFAULT 'pending',
            raw_sms TEXT,
            date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # 3. የካርድ መረጃዎች ሰንጠረዥ
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_cards (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER,
            stake REAL,
            card_data TEXT,
            game_id INTEGER DEFAULT 1
        )
    ''')
    
    # 4. የፕሮሞ ኮድ ሰንጠረዥ
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS promo_codes (
            code TEXT PRIMARY KEY,
            reward REAL,
            used INTEGER DEFAULT 0
        )
    ''')

    # 5. የቢንጎ ጨዋታዎች ሰንጠረዥ
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS games (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            status TEXT DEFAULT 'active',
            drawn_numbers TEXT DEFAULT '[]',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    conn.commit()
    conn.close()

init_db()

# ==========================================
# 1. RENDER KEEP-ALIVE
# ==========================================
@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "alive", "project": "Mereb Bingo"}), 200

# ==========================================
# 2. MINI APP FRONTEND
# ==========================================
@app.route('/')
def index():
    return render_template_string("""
        <!DOCTYPE html>
        <html lang="am">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Mereb Bingo Mini App</title>
            <script src="https://telegram.org/js/telegram-web-app.js"></script>
            <style>
                body { background-color: #17212b; color: #ffffff; font-family: Arial, sans-serif; margin: 0; padding: 15px; }
                .header { display: flex; align-items: center; justify-content: space-between; background: #242f3d; padding: 12px; border-radius: 10px; margin-bottom: 15px; }
                .balance-box { font-size: 14px; color: #4bc0c0; }
                .menu-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
                .menu-card { background: #242f3d; padding: 15px; border-radius: 8px; text-align: center; font-weight: bold; cursor: pointer; border: 1px solid #2b394a; }
                .menu-card:active { background: #2b394a; }
                .modal { display: none; position: fixed; bottom: 0; left: 0; right: 0; background: #1e2c3a; padding: 20px; border-top-left-radius: 15px; border-top-right-radius: 15px; box-shadow: 0 -5px 15px rgba(0,0,0,0.5); }
                input, textarea, button { width: 100%; padding: 12px; margin: 8px 0; border-radius: 6px; border: none; box-sizing: border-box; }
                button { background-color: #2481cc; color: white; font-weight: bold; cursor: pointer; }
            </style>
        </head>
        <body>
            <div class="header">
                <div>
                    <h3 style="margin:0;">ሜረብ ቢንጎ</h3>
                    <small id="user-display">Loading...</small>
                </div>
                <div class="balance-box">
                    ወጪ ሊደረግ የሚችል: <b id="main-balance">0.00</b> ETB
                </div>
            </div>

            <div class="menu-grid">
                <div class="menu-card" onclick="openSection('play')">🎮 Play (/play)</div>
                <div class="menu-card" onclick="openModal('deposit-modal')">📥 Deposit (/deposit)</div>
                <div class="menu-card" onclick="openSection('withdraw')">📤 Withdraw (/withdraw)</div>
                <div class="menu-card" onclick="openModal('transfer-modal')">💸 Transfer (/transfer)</div>
                <div class="menu-card" onclick="openSection('invite')">👥 Invite (/invite)</div>
                <div class="menu-card" onclick="openModal('promo-modal')">🎁 Promo Code (/promo)</div>
                <div class="menu-card" onclick="openSection('leaderboard')">🏆 Leaderboard</div>
                <div class="menu-card" onclick="openSection('support')">💬 Support</div>
            </div>

            <!-- Deposit Modal (Telebirr SMS Verification) -->
            <div id="deposit-modal" class="modal">
                <h4>በቴሌብር ሂሳብ መሙያ</h4>
                <p style="font-size: 12px; color: #aaa;">ገንዘቡን ወደ <b>0923410403 (Mulugeta Tilahun)</b> ከላኩ በኋላ ከቴሌብር የደረሰዎትን መልእክት (SMS) ከታች ባለው ሳጥን ውስጥ ለጥፈው ያረጋግጡ።</p>
                <textarea id="deposit-sms" rows="4" placeholder="ከቴሌብር የደረሰዎትን ሙሉ የጽሁፍ መልእክት (SMS) እዚህ ይለጥፉ..."></textarea>
                <button onclick="submitTelebirrSMS()">ማረጋገጫ ላክ (Verify Deposit)</button>
                <button style="background:#e53935;" onclick="closeModal('deposit-modal')">ዝጋ</button>
            </div>

            <!-- Transfer Modal -->
            <div id="transfer-modal" class="modal">
                <h4>Transfer from Main Wallet</h4>
                <p>Enter recipient's Telegram ID or Phone:</p>
                <input type="text" id="transfer-receiver" placeholder="የተቀባይ ID ወይም ስልክ">
                <input type="number" id="transfer-amount" placeholder="የገንዘብ መጠን (ETB)">
                <button onclick="submitTransfer()">አስተላልፍ (Transfer)</button>
                <button style="background:#e53935;" onclick="closeModal('transfer-modal')">ዝጋ</button>
            </div>

            <!-- Promo Modal -->
            <div id="promo-modal" class="modal">
                <h4>ፕሮሞ ኮድ ማስገቢያ</h4>
                <input type="text" id="promo-code-input" placeholder="ፕሮሞ ኮድ ያስገቡ">
                <button onclick="submitPromo()">ኮድ ተቀምስ (Redeem)</button>
                <button style="background:#e53935;" onclick="closeModal('promo-modal')">ዝጋ</button>
            </div>

            <script>
                const tg = window.Telegram.WebApp;
                tg.ready();
                tg.expand();

                const user = tg.initDataUnsafe?.user || { id: 12345678, first_name: "Demo User" };

                const urlParams = new URLSearchParams(window.location.search);
                const agentId = urlParams.get('startapp') || urlParams.get('start');

                fetch('/api/sync-user', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        telegram_id: user.id,
                        first_name: user.first_name,
                        agent_id: agentId ? parseInt(agentId.replace('ref_', '')) : null
                    })
                }).then(res => res.json()).then(data => {
                    if(data.status === 'success'){
                        document.getElementById('user-display').innerText = data.user.first_name;
                        document.getElementById('main-balance').innerText = data.user.balance.toFixed(2);
                    }
                });

                function openModal(id) { document.getElementById(id).style.display = 'block'; }
                function closeModal(id) { document.getElementById(id).style.display = 'none'; }

                function openSection(type) {
                    if (type === 'invite') {
                        fetch('/api/share-link', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ telegram_id: user.id })
                        }).then(r => r.json()).then(d => {
                            tg.openTelegramLink(d.telegram_share_button);
                        });
                    } else {
                        alert(type + " ገጽ በቅርብ ይከፈታል!");
                    }
                }

                function submitTelebirrSMS() {
                    const smsText = document.getElementById('deposit-sms').value;
                    if(!smsText.trim()) return alert("እባክዎን የቴሌብር SMS መልእክት ያስገቡ!");

                    fetch('/api/deposit-telebirr-sms', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ telegram_id: user.id, sms_text: smsText })
                    }).then(r => r.json()).then(res => {
                        alert(res.message || res.error);
                        if(res.status === 'success') location.reload();
                    });
                }

                function submitTransfer() {
                    const receiver = document.getElementById('transfer-receiver').value;
                    const amount = document.getElementById('transfer-amount').value;

                    fetch('/api/transfer', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ sender_id: user.id, receiver: receiver, amount: parseFloat(amount) })
                    }).then(r => r.json()).then(res => {
                        alert(res.message || res.error);
                        if(res.status === 'success') location.reload();
                    });
                }

                function submitPromo() {
                    const code = document.getElementById('promo-code-input').value;
                    fetch('/api/promo/redeem', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ telegram_id: user.id, code: code })
                    }).then(r => r.json()).then(res => {
                        alert(res.message || res.error);
                        if(res.status === 'success') location.reload();
                    });
                }
            </script>
        </body>
        </html>
    """)

# ==========================================
# 3. USER SYNC & REFERRAL LOGIC
# ==========================================
@app.route('/api/sync-user', methods=['POST'])
def sync_user():
    data = request.json or {}
    telegram_id = data.get('telegram_id')
    first_name = data.get('first_name', '')
    agent_id = data.get('agent_id')

    if not telegram_id:
        return jsonify({"error": "telegram_id ያስፈልጋል!"}), 400

    conn = get_db()
    cursor = conn.cursor()

    user = cursor.execute('SELECT * FROM users WHERE telegram_id = ?', (telegram_id,)).fetchone()

    if not user:
        cursor.execute('''
            INSERT INTO users (telegram_id, first_name, agent_id)
            VALUES (?, ?, ?)
        ''', (telegram_id, first_name, agent_id))

        if agent_id and agent_id != telegram_id:
            cursor.execute('''
                UPDATE users 
                SET commission_balance = commission_balance + ?, balance = balance + ? 
                WHERE telegram_id = ?
            ''', (REFERRAL_BONUS, REFERRAL_BONUS, agent_id))
    else:
        cursor.execute('UPDATE users SET first_name = ? WHERE telegram_id = ?', (first_name, telegram_id))

    conn.commit()
    updated_user = cursor.execute('SELECT * FROM users WHERE telegram_id = ?', (telegram_id,)).fetchone()
    conn.close()

    return jsonify({
        "status": "success",
        "user": {
            "telegram_id": updated_user['telegram_id'],
            "first_name": updated_user['first_name'],
            "balance": updated_user['balance'],
            "commission_balance": updated_user['commission_balance']
        }
    })

# ==========================================
# 4. AUTOMATIC TELEBIRR SMS VERIFICATION
# ==========================================
@app.route('/api/deposit-telebirr-sms', methods=['POST'])
def deposit_telebirr_sms():
    data = request.json or {}
    telegram_id = data.get('telegram_id')
    sms_text = str(data.get('sms_text', '')).strip()

    if not telegram_id or not sms_text:
        return jsonify({"error": "ትክክለኛ መረጃ አላስገቡም!"}), 400

    # 1. መልእክቱ ለ Mulugeta Tilahun (0923410403) መላኩን ማረጋገጥ
    if MERCHANT_PHONE not in sms_text and MERCHANT_NAME not in sms_text.upper():
        return jsonify({"error": f"የተሳሳተ የቴሌብር SMS! ክፍያው የተላከው ወደ {MERCHANT_PHONE} ({MERCHANT_NAME}) መሆኑን ያረጋግጡ።"}), 400

    # 2. የትራንዛክሽን ቁጥር (Transaction ID) በ Regex ማውጣት (ለምሳሌ፡ 10A2B3C4D5 ወይም ተመሳሳይ ፎርማት)
    tx_match = re.search(r'\b([A-Z0-9]{10,})\b', sms_text.upper())
    if not tx_match:
        return jsonify({"error": "በትራንስክሪፕቱ ላይ የትራንዛክሽን ቁጥር ማግኘት አልተቻለም!"}), 400
    
    tx_id = tx_match.group(1)

    # 3. የገንዘብ መጠን ማውጣት (ETB / ብር)
    amount_match = re.search(r'(?:ETB|ብር)\s*([\d\.]+)|([\d\.]+)\s*(?:ETB|ብር)', sms_text, re.IGNORECASE)
    if not amount_match:
        return jsonify({"error": "የክፍያውን የገንዘብ መጠን ማረጋገጥ አልተቻለም!"}), 400

    amount_str = amount_match.group(1) or amount_match.group(2)
    try:
        amount = float(amount_str)
    except ValueError:
        return jsonify({"error": "የገንዘብ መጠኑ የተሳሳተ ነው!"}), 400

    conn = get_db()
    cursor = conn.cursor()

    # 4. የትራንዛክሽን ቁጥሩ ቀደም ሲል ጥቅም ላይ መዋሉን ማረጋገጥ
    existing = cursor.execute('SELECT id FROM transactions WHERE tx_id = ?', (tx_id,)).fetchone()
    if existing:
        conn.close()
        return jsonify({"error": "ይህ የትራንዛክሽን ቁጥር ቀደም ሲል ጥቅም ላይ ውሏል!"}), 400

    # 5. ሂሳቡን ማጽደቅ እና ዳታቤዝ ላይ መጨመር
    try:
        cursor.execute('''
            INSERT INTO transactions (telegram_id, tx_id, amount, type, method, status, raw_sms)
            VALUES (?, ?, ?, 'deposit', 'telebirr_sms', 'approved', ?)
        ''', (telegram_id, tx_id, amount, sms_text))

        cursor.execute('UPDATE users SET balance = balance + ? WHERE telegram_id = ?', (amount, telegram_id))

        conn.commit()
        updated_user = cursor.execute('SELECT balance FROM users WHERE telegram_id = ?', (telegram_id,)).fetchone()
        conn.close()

        return jsonify({
            "status": "success", 
            "message": f"በስኬት ተረጋገጠ! {amount} ETB ወደ አካውንትዎ ተጨምሯል።", 
            "new_balance": updated_user['balance']
        })
    except Exception as e:
        conn.rollback()
        conn.close()
        return jsonify({"error": f"ስህተት ተከሰተ፡ {str(e)}"}), 500

# ==========================================
# 5. WALLET TRANSFER
# ==========================================
@app.route('/api/transfer', methods=['POST'])
def transfer_money():
    data = request.json or {}
    sender_id = data.get('sender_id')
    receiver = str(data.get('receiver', '')).strip()
    amount = float(data.get('amount', 0))

    if amount <= 0 or not sender_id or not receiver:
        return jsonify({"error": "ትክክለኛ መረጃ አላስገቡም!"}), 400

    conn = get_db()
    cursor = conn.cursor()

    sender = cursor.execute('SELECT balance FROM users WHERE telegram_id = ?', (sender_id,)).fetchone()
    if not sender or sender['balance'] < amount:
        conn.close()
        return jsonify({"error": "በቂ ባላንስ የሎትም!"}), 400

    recipient = cursor.execute('SELECT telegram_id FROM users WHERE telegram_id = ? OR phone_number = ?', (receiver, receiver)).fetchone()
    if not recipient:
        conn.close()
        return jsonify({"error": "ተቀባዩ አልተገኘም!"}), 404

    cursor.execute('UPDATE users SET balance = balance - ? WHERE telegram_id = ?', (amount, sender_id))
    cursor.execute('UPDATE users SET balance = balance + ? WHERE telegram_id = ?', (amount, recipient['telegram_id']))

    cursor.execute('''
        INSERT INTO transactions (telegram_id, amount, type, method, status)
        VALUES (?, ?, 'transfer_out', 'wallet', 'approved')
    ''', (sender_id, amount))

    conn.commit()
    conn.close()

    return jsonify({"status": "success", "message": f"{amount} ETB በስኬት ተላክቷል!"})

# ==========================================
# 6. SHARE LINK & PROMO CODES
# ==========================================
@app.route('/api/share-link', methods=['POST'])
def share_link():
    data = request.json or {}
    telegram_id = data.get('telegram_id')
    mini_app_link = f"https://t.me/{BOT_USERNAME}/app?startapp=ref_{telegram_id}"
    share_text = "🎯 በ«ሜረብ ቢንጎ» ተጫውተው ይሸልሙ! አሁኑኑ ይቀላቀሉ፡"
    encoded_text = urllib.parse.quote(share_text)
    
    return jsonify({
        "status": "success",
        "telegram_share_button": f"https://t.me/share/url?url={mini_app_link}&text={encoded_text}"
    })

@app.route('/api/promo/redeem', methods=['POST'])
def redeem_promo():
    data = request.json or {}
    telegram_id = data.get('telegram_id')
    code = str(data.get('code', '')).strip().upper()

    conn = get_db()
    cursor = conn.cursor()

    promo = cursor.execute('SELECT * FROM promo_codes WHERE code = ? AND used = 0', (code,)).fetchone()
    if not promo:
        conn.close()
        return jsonify({"error": "የተሳሳተ ወይም ጥቅም ላይ የዋለ ፕሮሞ ኮድ!"}), 400

    cursor.execute('UPDATE promo_codes SET used = 1 WHERE code = ?', (code,))
    cursor.execute('UPDATE users SET balance = balance + ? WHERE telegram_id = ?', (promo['reward'], telegram_id))

    conn.commit()
    conn.close()

    return jsonify({"status": "success", "message": f"እንኳን ደስ አለዎት! {promo['reward']} ETB ቦነስ አግኝተዋል።"})

# ==========================================
# 7. SERVER-SIDE BINGO ENGINE
# ==========================================
@app.route('/api/game/create-card', methods=['POST'])
def create_card():
    data = request.json or {}
    telegram_id = data.get('telegram_id')
    stake = float(data.get('stake', 10.0))

    conn = get_db()
    cursor = conn.cursor()

    user = cursor.execute('SELECT balance FROM users WHERE telegram_id = ?', (telegram_id,)).fetchone()
    if not user or user['balance'] < stake:
        conn.close()
        return jsonify({"error": "በቂ ባላንስ የሎትም!"}), 400

    cursor.execute('UPDATE users SET balance = balance - ? WHERE telegram_id = ?', (stake, telegram_id))

    card = {
        'B': random.sample(range(1, 16), 5),
        'I': random.sample(range(16, 31), 5),
        'N': random.sample(range(31, 46), 5),
        'G': random.sample(range(46, 61), 5),
        'O': random.sample(range(61, 76), 5)
    }
    card['N'][2] = 'FREE'

    cursor.execute('INSERT INTO user_cards (telegram_id, stake, card_data) VALUES (?, ?, ?)', 
                   (telegram_id, stake, json.dumps(card)))

    conn.commit()
    conn.close()

    return jsonify({"status": "success", "card": card})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))

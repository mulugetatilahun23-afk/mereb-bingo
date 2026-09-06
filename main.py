from flask import Flask, request, jsonify, render_template_string
import sqlite3
import os
import re
import json
import random
from datetime import datetime

app = Flask(__name__)

# ==========================================
# CONFIGURATION
# ==========================================
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
BOT_USERNAME = os.environ.get("BOT_USERNAME", "MerebBingoBot")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "123456789"))  # Telegram ID እዚህ ይተኩ

DB_NAME = 'mereb_bingo.db'
MERCHANT_PHONE = "0923410403"
MERCHANT_NAME = "MULUGETA TILAHUN"
REFERRAL_BONUS = 5.0
COMMISSION_RATE = 0.20

# ==========================================
# DATABASE SETUP & AUTO-MIGRATION
# ==========================================
def get_db():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()
    
    # Users Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            telegram_id INTEGER PRIMARY KEY, 
            first_name TEXT,
            phone_number TEXT, 
            balance REAL DEFAULT 0.0, 
            commission_balance REAL DEFAULT 0.0,
            agent_id INTEGER,
            is_admin INTEGER DEFAULT 0,
            is_agent INTEGER DEFAULT 0
        )
    ''')

    # ነባር DB ላይ ኮለሞች ከሌሉ አውቶማቲክ ማስተካከያ (Migration)
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN is_agent INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass

    try:
        cursor.execute("ALTER TABLE users ADD COLUMN is_admin INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER,
            tx_id TEXT,
            amount REAL,
            type TEXT,
            method TEXT,
            status TEXT DEFAULT 'pending',
            raw_sms TEXT,
            date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_cards (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER,
            cartella_number INTEGER,
            stake REAL,
            card_data TEXT,
            game_id INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS promo_codes (
            code TEXT PRIMARY KEY,
            reward REAL,
            used INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

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
# HELPER FUNCTIONS
# ==========================================
def is_admin_user(telegram_id):
    if not telegram_id:
        return False
    return int(telegram_id) == ADMIN_ID

# ==========================================
# PUBLIC & HEALTH ENDPOINTS
# ==========================================
@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "alive", "project": "Mereb Bingo"}), 200

# ==========================================
# USER SERVICES & TRANSACTIONS
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
            INSERT INTO users (telegram_id, first_name, agent_id, is_agent)
            VALUES (?, ?, ?, 0)
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
            "commission_balance": updated_user['commission_balance'],
            "is_agent": updated_user['is_agent'] if 'is_agent' in updated_user.keys() else 0
        }
    })

@app.route('/api/deposit-telebirr-sms', methods=['POST'])
def deposit_telebirr_sms():
    data = request.json or {}
    telegram_id = data.get('telegram_id')
    sms_text = str(data.get('sms_text', '')).strip()

    if not telegram_id or not sms_text:
        return jsonify({"error": "ትክክለኛ መረጃ አላስገቡም!"}), 400

    if MERCHANT_PHONE not in sms_text and MERCHANT_NAME not in sms_text.upper():
        return jsonify({"error": f"የተሳሳተ SMS! ክፍያው ወደ {MERCHANT_PHONE} ({MERCHANT_NAME}) መላኩን ያረጋግጡ።"}), 400

    tx_match = re.search(r'\b([A-Z0-9]{10,})\b', sms_text.upper())
    if not tx_match:
        return jsonify({"error": "በትራንስክሪፕቱ ላይ የትራንዛክሽን ቁጥር ማግኘት አልተቻለም!"}), 400
    
    tx_id = tx_match.group(1)

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

    existing = cursor.execute('SELECT id FROM transactions WHERE tx_id = ?', (tx_id,)).fetchone()
    if existing:
        conn.close()
        return jsonify({"error": "ይህ የትራንዛክሽን ቁጥር ቀደም ሲል ጥቅም ላይ ውሏል!"}), 400

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

@app.route('/api/withdraw', methods=['POST'])
def withdraw():
    data = request.json or {}
    telegram_id = data.get('telegram_id')
    amount = float(data.get('amount', 0))
    phone = data.get('phone', '')

    if not telegram_id or amount <= 0 or not phone:
        return jsonify({"error": "ትክክለኛ መረጃ ያስገቡ!"}), 400

    conn = get_db()
    cursor = conn.cursor()

    user = cursor.execute('SELECT balance FROM users WHERE telegram_id = ?', (telegram_id,)).fetchone()
    if not user or user['balance'] < amount:
        conn.close()
        return jsonify({"error": "በቂ የሂሳብ መጠን የሎትም!"}), 400

    cursor.execute('UPDATE users SET balance = balance - ? WHERE telegram_id = ?', (amount, telegram_id))
    cursor.execute('INSERT INTO transactions (telegram_id, amount, type, method, status) VALUES (?, ?, "withdraw", ?, "pending")', (telegram_id, amount, phone))

    conn.commit()
    conn.close()

    return jsonify({"status": "success", "message": "የወጪ ጥያቄዎ በቀጣይነት ተመዝግቧል። በአድሚኑ ተመርምሮ ይለቀቃል!"})

@app.route('/api/transfer', methods=['POST'])
def transfer():
    data = request.json or {}
    sender_id = data.get('telegram_id')
    receiver_id = data.get('receiver_id')
    amount = float(data.get('amount', 0))

    if not sender_id or not receiver_id or amount <= 0:
        return jsonify({"error": "ትክክለኛ መረጃ ያስገቡ!"}), 400

    if str(sender_id) == str(receiver_id):
        return jsonify({"error": "ወደ ራስዎ ማስተላለፍ አይችሉም!"}), 400

    conn = get_db()
    cursor = conn.cursor()

    sender = cursor.execute('SELECT balance FROM users WHERE telegram_id = ?', (sender_id,)).fetchone()
    receiver = cursor.execute('SELECT telegram_id FROM users WHERE telegram_id = ?', (receiver_id,)).fetchone()

    if not sender or sender['balance'] < amount:
        conn.close()
        return jsonify({"error": "በቂ የሂሳብ መጠን የሎትም!"}), 400

    if not receiver:
        conn.close()
        return jsonify({"error": "የተቀባዩ አካውንት አልተገኘም!"}), 404

    cursor.execute('UPDATE users SET balance = balance - ? WHERE telegram_id = ?', (amount, sender_id))
    cursor.execute('UPDATE users SET balance = balance + ? WHERE telegram_id = ?', (amount, receiver_id))

    cursor.execute('INSERT INTO transactions (telegram_id, amount, type, method, status) VALUES (?, ?, "transfer_out", ?, "approved")', (sender_id, amount, receiver_id))
    cursor.execute('INSERT INTO transactions (telegram_id, amount, type, method, status) VALUES (?, ?, "transfer_in", ?, "approved")', (receiver_id, amount, sender_id))

    conn.commit()
    conn.close()

    return jsonify({"status": "success", "message": f"{amount} ETB ለተጠቃሚ {receiver_id} በስኬት አስተላልፈዋል!"})

@app.route('/api/use-promo', methods=['POST'])
def use_promo():
    data = request.json or {}
    telegram_id = data.get('telegram_id')
    code = str(data.get('code', '')).strip().upper()

    if not telegram_id or not code:
        return jsonify({"error": "ትክክለኛ መረጃ ያስገቡ!"}), 400

    conn = get_db()
    cursor = conn.cursor()

    promo = cursor.execute('SELECT * FROM promo_codes WHERE code = ? AND used = 0', (code,)).fetchone()
    if not promo:
        conn.close()
        return jsonify({"error": "የተሳሳተ ወይም ጥቅም ላይ የዋለ ፕሮሞ ኮድ!"}), 400

    cursor.execute('UPDATE promo_codes SET used = 1 WHERE code = ?', (code,))
    cursor.execute('UPDATE users SET balance = balance + ? WHERE telegram_id = ?', (promo['reward'], telegram_id))
    cursor.execute('INSERT INTO transactions (telegram_id, amount, type, method, status) VALUES (?, ?, "promo", ?, "approved")', (telegram_id, promo['reward'], code))

    conn.commit()
    conn.close()

    return jsonify({"status": "success", "message": f"እንኳን ደስ አለዎት! {promo['reward']} ETB ቦነስ አግኝተዋል።"})

@app.route('/api/leaderboard', methods=['GET'])
def leaderboard():
    conn = get_db()
    cursor = conn.cursor()
    top_users = cursor.execute('SELECT first_name, balance FROM users ORDER BY balance DESC LIMIT 10').fetchall()
    conn.close()

    result = [{"first_name": u['first_name'] or 'Anonymous', "balance": u['balance']} for u in top_users]
    return jsonify({"status": "success", "leaderboard": result})

# ==========================================
# ADMIN ENDPOINTS
# ==========================================
@app.route('/api/admin/dashboard', methods=['POST'])
def admin_dashboard():
    data = request.json or {}
    admin_id = data.get('admin_id')

    if not is_admin_user(admin_id):
        return jsonify({"error": "ለዚህ ተግባር ፈቃድ የሎትም!"}), 403

    conn = get_db()
    cursor = conn.cursor()

    total_users = cursor.execute('SELECT COUNT(*) as count FROM users').fetchone()['count']
    total_balance = cursor.execute('SELECT SUM(balance) as total FROM users').fetchone()['total'] or 0.0
    pending_deposits = cursor.execute("SELECT COUNT(*) as count FROM transactions WHERE type='deposit' AND status='pending'").fetchone()['count']
    pending_withdrawals = cursor.execute("SELECT COUNT(*) as count FROM transactions WHERE type='withdraw' AND status='pending'").fetchone()['count']

    conn.close()
    return jsonify({
        "status": "success",
        "total_users": total_users,
        "total_user_balance": total_balance,
        "pending_deposits": pending_deposits,
        "pending_withdrawals": pending_withdrawals
    })

@app.route('/api/admin/add-balance', methods=['POST'])
def admin_add_balance():
    data = request.json or {}
    admin_id = data.get('admin_id')
    target_id = data.get('target_telegram_id')
    amount = float(data.get('amount', 0))

    if not is_admin_user(admin_id):
        return jsonify({"error": "ለዚህ ተግባር ፈቃድ የሎትም!"}), 403

    if not target_id or amount <= 0:
        return jsonify({"error": "ትክክለኛ የተጠቃሚ ID እና የገንዘብ መጠን ያስገቡ!"}), 400

    conn = get_db()
    cursor = conn.cursor()

    user = cursor.execute('SELECT telegram_id FROM users WHERE telegram_id = ?', (target_id,)).fetchone()
    if not user:
        conn.close()
        return jsonify({"error": "ተጠቃሚው አልተገኘም!"}), 404

    cursor.execute('UPDATE users SET balance = balance + ? WHERE telegram_id = ?', (amount, target_id))
    cursor.execute('INSERT INTO transactions (telegram_id, amount, type, method, status) VALUES (?, ?, "manual_deposit", "admin", "approved")', (target_id, amount))

    conn.commit()
    conn.close()

    return jsonify({"status": "success", "message": f"ለተጠቃሚ {target_id} መጠን {amount} ETB በስኬት ተጨምሯል!"})

# ==========================================
# FRONTEND MINI APP RENDER
# ==========================================
@app.route('/')
def index():
    return render_template_string("""
        <!DOCTYPE html>
        <html lang="am">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Mereb Bingo</title>
            <script src="https://telegram.org/js/telegram-web-app.js"></script>
            <style>
                body { background-color: #0d141e; color: #ffffff; font-family: Arial, sans-serif; margin: 0; padding: 12px; }
                .header { display: flex; align-items: center; justify-content: space-between; background: #16212e; padding: 12px; border-radius: 10px; margin-bottom: 12px; }
                .balance-box { font-size: 13px; color: #4bc0c0; text-align: right; }
                .menu-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
                .menu-card { background: #16212e; padding: 14px; border-radius: 8px; text-align: center; font-weight: bold; cursor: pointer; border: 1px solid #233346; font-size: 14px; }
                .menu-card:active { background: #233346; }
                .modal { display: none; position: fixed; bottom: 0; left: 0; right: 0; background: #15202d; padding: 20px; border-top-left-radius: 15px; border-top-right-radius: 15px; box-shadow: 0 -5px 15px rgba(0,0,0,0.5); z-index: 100; max-height: 80vh; overflow-y: auto; }
                input, textarea, button { width: 100%; padding: 12px; margin: 8px 0; border-radius: 6px; border: none; box-sizing: border-box; }
                input, textarea { background: #1c2938; color: #fff; border: 1px solid #2d415a; }
                button { background-color: #2481cc; color: white; font-weight: bold; cursor: pointer; }
                .stake-opts { display: flex; gap: 10px; margin: 10px 0; }
                .stake-btn { background: #1e2c3d; border: 1px solid #324760; color: #fff; flex: 1; padding: 12px; border-radius: 8px; font-size: 16px; font-weight: bold; }
                .stake-btn.selected { background: #00c853; border-color: #00c853; }
                .leaderboard-list { list-style: none; padding: 0; margin: 0; }
                .leaderboard-item { display: flex; justify-content: space-between; padding: 10px; background: #1c2938; border-bottom: 1px solid #2b3b4e; border-radius: 6px; margin-bottom: 6px; }
            </style>
        </head>
        <body>
            <div id="home-view">
                <div class="header">
                    <div>
                        <h3 style="margin:0;">መረብ ቢንጎ</h3>
                        <small id="user-display">Loading...</small>
                    </div>
                    <div class="balance-box">
                        ወጪ ሊደረግ የሚችል: <br><b id="main-balance">0.00</b> ETB
                    </div>
                </div>

                <div class="menu-grid">
                    <div class="menu-card" onclick="openModal('stake-modal')">🎮 Play (/play)</div>
                    <div class="menu-card" onclick="openModal('deposit-modal')">📥 Deposit (/deposit)</div>
                    <div class="menu-card" onclick="openModal('withdraw-modal')">📤 Withdraw (/withdraw)</div>
                    <div class="menu-card" onclick="openModal('transfer-modal')">💸 Transfer (/transfer)</div>
                    <div class="menu-card" onclick="openModal('promo-modal')">🎁 Promo Code (/promo)</div>
                    <div class="menu-card" onclick="openModal('invite-modal')">👥 Invite (/invite)</div>
                    <div class="menu-card" onclick="loadLeaderboard()">🏆 Leaderboard</div>
                    <div class="menu-card" onclick="openModal('support-modal')">🎧 Support (/support)</div>
                </div>
            </div>

            <!-- Deposit Modal -->
            <div id="deposit-modal" class="modal">
                <h4>በቴሌብር ሂሳብ መሙያ</h4>
                <p style="font-size: 12px; color: #aaa;">ገንዘቡን ወደ <b>0923410403 (Mulugeta Tilahun)</b> ከላኩ በኋላ ከቴሌብር የደረሰዎትን SMS እዚህ ይለጥፉ።</p>
                <textarea id="deposit-sms" rows="4" placeholder="ከቴሌብር የደረሰዎትን ሙሉ SMS ይለጥፉ..."></textarea>
                <button onclick="submitTelebirrSMS()">ማረጋገጫ ላክ (Verify)</button>
                <button style="background:#e53935;" onclick="closeModal('deposit-modal')">ዝጋ</button>
            </div>

            <!-- Withdraw Modal -->
            <div id="withdraw-modal" class="modal">
                <h4>ገንዘብ ወጪ ማድረጊያ</h4>
                <input type="number" id="withdraw-amount" placeholder="የገንዘብ መጠን (ETB)">
                <input type="text" id="withdraw-phone" placeholder="የቴሌብር ስልክ ቁጥር (09...)">
                <button onclick="submitWithdrawal()">ወጪ ለማድረግ ጠይቅ</button>
                <button style="background:#e53935;" onclick="closeModal('withdraw-modal')">ዝጋ</button>
            </div>

            <!-- Transfer Modal -->
            <div id="transfer-modal" class="modal">
                <h4>ለሌላ ተጠቃሚ ብር ማስተላለፊያ</h4>
                <input type="number" id="transfer-receiver" placeholder="የተቀባይ Telegram ID">
                <input type="number" id="transfer-amount" placeholder="የገንዘብ መጠን (ETB)">
                <button onclick="submitTransfer()">ብር አስተላልፍ</button>
                <button style="background:#e53935;" onclick="closeModal('transfer-modal')">ዝጋ</button>
            </div>

            <!-- Promo Modal -->
            <div id="promo-modal" class="modal">
                <h4>ፕሮሞ ኮድ ያስገቡ</h4>
                <input type="text" id="promo-code-input" placeholder="ለምሳሌ: BINGO2026">
                <button onclick="submitPromoCode()">ኮዱን ተቀምጥ</button>
                <button style="background:#e53935;" onclick="closeModal('promo-modal')">ዝጋ</button>
            </div>

            <!-- Invite Modal -->
            <div id="invite-modal" class="modal">
                <h4>ጓደኞችን ይጋብዙ!</h4>
                <p style="font-size: 13px; color: #aaa;">የእርስዎን የጋባዥ ሊንክ በመጠቀም ለሚመዘገብ ለእያንዳንዱ ጓደኛዎት <b>5 ETB</b> ቦነስ ያገኛሉ።</p>
                <input type="text" id="invite-link-input" readonly>
                <button onclick="copyInviteLink()">ሊንኩን ኮፒ አድርግ</button>
                <button style="background:#e53935;" onclick="closeModal('invite-modal')">ዝጋ</button>
            </div>

            <!-- Leaderboard Modal -->
            <div id="leaderboard-modal" class="modal">
                <h4>🏆 ከፍተኛ አሸናፊዎች</h4>
                <div id="leaderboard-container">Loading...</div>
                <button style="background:#e53935; margin-top: 10px;" onclick="closeModal('leaderboard-modal')">ዝጋ</button>
            </div>

            <!-- Support Modal -->
            <div id="support-modal" class="modal">
                <h4>🎧 የእርዳታ ማዕከል</h4>
                <p style="font-size: 13px;">ለማንኛውም ጥያቄ ወይም ችግር በአድሚን አድራሻችን ያግኙን፡</p>
                <p style="text-align: center; font-weight: bold; color: #4bc0c0;">@MerebSupportBot</p>
                <button style="background:#e53935;" onclick="closeModal('support-modal')">ዝጋ</button>
            </div>

            <!-- Stake Selection Modal -->
            <div id="stake-modal" class="modal">
                <h4 style="margin-top:0;">የመወራረጃ መጠን ይምረጡ (Stake)</h4>
                <div class="stake-opts">
                    <button class="stake-btn selected" id="stake-10" onclick="setStake(10)">10 ETB</button>
                    <button class="stake-btn" id="stake-20" onclick="setStake(20)">20 ETB</button>
                    <button class="stake-btn" id="stake-30" onclick="setStake(30)">30 ETB</button>
                </div>
                <button onclick="alert('ጨዋታው በቅርብ ይጀምራል!')">ቀጥል</button>
                <button style="background:#e53935;" onclick="closeModal('stake-modal')">ተመለስ</button>
            </div>

            <script>
                const tg = window.Telegram.WebApp;
                tg.ready();
                tg.expand();

                const user = tg.initDataUnsafe?.user || { id: 12345678, first_name: "Demo User" };
                let currentStake = 10;

                // Invite Link
                document.getElementById('invite-link-input').value = `https://t.me/${BOT_USERNAME}?start=${user.id}`;

                fetch('/api/sync-user', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ telegram_id: user.id, first_name: user.first_name })
                })
                .then(res => {
                    if (!res.ok) throw new Error("Server Error: " + res.status);
                    return res.json();
                })
                .then(data => {
                    if(data.status === 'success'){
                        document.getElementById('user-display').innerText = data.user.first_name;
                        document.getElementById('main-balance').innerText = data.user.balance.toFixed(2);
                    }
                })
                .catch(err => {
                    console.error("Sync Error:", err);
                    document.getElementById('user-display').innerText = user.first_name || "ተጠቃሚ";
                });

                function openModal(id) { document.getElementById(id).style.display = 'block'; }
                function closeModal(id) { document.getElementById(id).style.display = 'none'; }
                function setStake(amount) { currentStake = amount; }

                function copyInviteLink() {
                    const copyText = document.getElementById("invite-link-input");
                    copyText.select();
                    document.execCommand("copy");
                    alert("የመጋበዣ ሊንክዎ ተገልብጧል!");
                }

                function submitTelebirrSMS() {
                    const smsText = document.getElementById('deposit-sms').value;
                    if(!smsText.trim()) return alert("እባክዎን SMS ያስገቡ!");

                    fetch('/api/deposit-telebirr-sms', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ telegram_id: user.id, sms_text: smsText })
                    }).then(r => r.json()).then(res => {
                        alert(res.message || res.error);
                        if(res.status === 'success') location.reload();
                    });
                }

                function submitWithdrawal() {
                    const amount = document.getElementById('withdraw-amount').value;
                    const phone = document.getElementById('withdraw-phone').value;

                    if(!amount || !phone) return alert("እባክዎን ሁሉንም መስኮች ይሙሉ!");

                    fetch('/api/withdraw', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ telegram_id: user.id, amount: amount, phone: phone })
                    }).then(r => r.json()).then(res => {
                        alert(res.message || res.error);
                        if(res.status === 'success') closeModal('withdraw-modal');
                    });
                }

                function submitTransfer() {
                    const receiverId = document.getElementById('transfer-receiver').value;
                    const amount = document.getElementById('transfer-amount').value;

                    if(!receiverId || !amount) return alert("እባክዎን ሁሉንም መስኮች ይሙሉ!");

                    fetch('/api/transfer', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ telegram_id: user.id, receiver_id: receiverId, amount: amount })
                    }).then(r => r.json()).then(res => {
                        alert(res.message || res.error);
                        if(res.status === 'success') location.reload();
                    });
                }

                function submitPromoCode() {
                    const code = document.getElementById('promo-code-input').value;
                    if(!code.trim()) return alert("እባክዎን ኮድ ያስገቡ!");

                    fetch('/api/use-promo', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ telegram_id: user.id, code: code })
                    }).then(r => r.json()).then(res => {
                        alert(res.message || res.error);
                        if(res.status === 'success') location.reload();
                    });
                }

                function loadLeaderboard() {
                    openModal('leaderboard-modal');
                    fetch('/api/leaderboard')
                    .then(r => r.json())
                    .then(res => {
                        if(res.status === 'success'){
                            let html = '<ul class="leaderboard-list">';
                            res.leaderboard.forEach((u, i) => {
                                html += `<li class="leaderboard-item"><span>${i+1}. ${u.first_name}</span><b>${u.balance.toFixed(2)} ETB</b></li>`;
                            });
                            html += '</ul>';
                            document.getElementById('leaderboard-container').innerHTML = html;
                        }
                    });
                }
            </script>
        </body>
        </html>
    """)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))

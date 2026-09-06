from flask import Flask, request, jsonify, render_template_string
import sqlite3
import os
import random
import json
import re
import urllib.parse
from datetime import datetime

app = Flask(__name__)

# Environment Variables
BOT_TOKEN = os.environ.get("8967099088:AAEpqyu1ZMb8THzF40ZSwFUZxq43dH-oPYA", "")
BOT_USERNAME = os.environ.get("BOT_USERNAME", "MerebBingoBot")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "123456789"))  # የእርስዎን Telegram ID እዚህ ያግኙ
DB_NAME = 'mereb_bingo.db'

MERCHANT_PHONE = "0923410403"
MERCHANT_NAME = "MULUGETA TILAHUN"
REFERRAL_BONUS = 5.0
DAILY_LIMIT = 2000.0  
MIN_REMAINING_BALANCE = 50.0  
COMMISSION_RATE = 0.20  

def get_db():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            telegram_id INTEGER PRIMARY KEY, 
            first_name TEXT,
            phone_number TEXT, 
            balance REAL DEFAULT 0.0, 
            commission_balance REAL DEFAULT 0.0,
            agent_id INTEGER,
            is_admin INTEGER DEFAULT 0
        )
    ''')
    
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

def is_admin_user(telegram_id):
    return int(telegram_id) == ADMIN_ID

@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "alive", "project": "Mereb Bingo"}), 200

# ==========================================
# ADMIN ENDPOINTS (የአድሚን መቆጣጠሪያዎች)
# ==========================================

# 1. የአድሚን ዳሽቦርድ መረጃ (የተጠቃሚ ብዛት፣ የተቀመጠ ብር፣ ወዘተ)
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

# 2. ለተጠቃሚ በእጅ ሂሳብ መሙላት (Manual Deposit)
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

# 3. የያዘውን የተቀማጭ/የወጪ ጥያቄ ማጽደቅ (Approve Pending Transaction)
@app.route('/api/admin/approve-transaction', methods=['POST'])
def admin_approve_tx():
    data = request.json or {}
    admin_id = data.get('admin_id')
    tx_id = data.get('tx_id')

    if not is_admin_user(admin_id):
        return jsonify({"error": "ለዚህ ተግባር ፈቃድ የሎትም!"}), 403

    conn = get_db()
    cursor = conn.cursor()

    tx = cursor.execute('SELECT * FROM transactions WHERE id = ? AND status = "pending"', (tx_id,)).fetchone()
    if not tx:
        conn.close()
        return jsonify({"error": "የተጠየቀው ትራንዛክሽን አልተገኘም ወይም ጸድቋል!"}), 404

    if tx['type'] == 'deposit':
        cursor.execute('UPDATE users SET balance = balance + ? WHERE telegram_id = ?', (tx['amount'], tx['telegram_id']))
    
    cursor.execute('UPDATE transactions SET status = "approved" WHERE id = ?', (tx_id,))

    conn.commit()
    conn.close()

    return jsonify({"status": "success", "message": f"ትራንዛክሽን #{tx_id} በስኬት ጸድቋል!"})

# 4. አዲስ ፕሮሞ ኮድ መፍጠር (Create Promo Code)
@app.route('/api/admin/create-promo', methods=['POST'])
def admin_create_promo():
    data = request.json or {}
    admin_id = data.get('admin_id')
    code = str(data.get('code', '')).strip().upper()
    reward = float(data.get('reward', 0))

    if not is_admin_user(admin_id):
        return jsonify({"error": "ለዚህ ተግባር ፈቃድ የሎትም!"}), 403

    if not code or reward <= 0:
        return jsonify({"error": "ትክክለኛ ኮድ እና የቦነስ መጠን ያስገቡ!"}), 400

    conn = get_db()
    cursor = conn.cursor()

    try:
        cursor.execute('INSERT INTO promo_codes (code, reward) VALUES (?, ?)', (code, reward))
        conn.commit()
        conn.close()
        return jsonify({"status": "success", "message": f"ፕሮሞ ኮድ '{code}' በ {reward} ETB ቦነስ ተፈጥሯል!"})
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({"error": "ይህ ፕሮሞ ኮድ አስቀድሞ አለ!"}), 400

# ==========================================
# FRONTEND MINI APP (USER / FRONTEND)
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
                .balance-box { font-size: 13px; color: #4bc0c0; }
                .menu-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
                .menu-card { background: #16212e; padding: 14px; border-radius: 8px; text-align: center; font-weight: bold; cursor: pointer; border: 1px solid #233346; }
                .menu-card:active { background: #233346; }
                .page-view { display: none; }
                .active-view { display: block; }
                .modal { display: none; position: fixed; bottom: 0; left: 0; right: 0; background: #15202d; padding: 20px; border-top-left-radius: 15px; border-top-right-radius: 15px; box-shadow: 0 -5px 15px rgba(0,0,0,0.5); z-index: 100; }
                input, textarea, button { width: 100%; padding: 12px; margin: 8px 0; border-radius: 6px; border: none; box-sizing: border-box; }
                button { background-color: #2481cc; color: white; font-weight: bold; cursor: pointer; }
                .stake-opts { display: flex; gap: 10px; margin: 10px 0; }
                .stake-btn { background: #1e2c3d; border: 1px solid #324760; color: #fff; flex: 1; padding: 12px; border-radius: 8px; font-size: 16px; font-weight: bold; }
                .stake-btn.selected { background: #00c853; border-color: #00c853; }
                .cartella-header { display: flex; justify-content: space-between; background: #16212e; padding: 10px; border-radius: 8px; font-size: 12px; margin-bottom: 10px; text-align: center; }
                .cartella-grid { display: grid; grid-template-columns: repeat(10, 1fr); gap: 4px; max-height: 350px; overflow-y: auto; background: #111a26; padding: 8px; border-radius: 8px; }
                .cartella-num { background: #1c2938; border: 1px solid #2a3d54; color: #fff; text-align: center; padding: 8px 0; border-radius: 50%; font-size: 11px; font-weight: bold; cursor: pointer; }
                .cartella-num.selected { background: #ff5252; border-color: #ff5252; }
                .bingo-card { background: #16212e; padding: 12px; border-radius: 12px; max-width: 340px; margin: 0 auto; border: 1px solid #253549; }
                .bingo-grid { display: grid; grid-template-columns: repeat(5, 1fr); gap: 6px; margin-top: 10px; }
                .bingo-cell { background: #223144; color: #fff; text-align: center; height: 48px; display: flex; align-items: center; justify-content: center; font-weight: bold; border-radius: 6px; font-size: 15px; }
                .bingo-cell.header-cell { background: #2d415a; color: #4bc0c0; font-size: 16px; font-weight: 900; }
                .bingo-cell.star-cell { background: #00c853; color: #fff; font-size: 20px; }
                .winner-banner { background: linear-gradient(135deg, #1e3c72, #2a5298); padding: 12px; border-radius: 10px; text-align: center; margin-bottom: 15px; border: 1px solid #ffb300; }
            </style>
        </head>
        <body>
            <div id="home-view" class="page-view active-view">
                <div class="header">
                    <div>
                        <h3 style="margin:0;">መረብ ቢንጎ</h3>
                        <small id="user-display">Loading...</small>
                    </div>
                    <div class="balance-box">
                        ወጪ ሊደረግ የሚችል: <b id="main-balance">0.00</b> ETB
                    </div>
                </div>

                <div class="menu-grid">
                    <div class="menu-card" onclick="openModal('stake-modal')">🎮 Play (/play)</div>
                    <div class="menu-card" onclick="openModal('deposit-modal')">📥 Deposit (/deposit)</div>
                    <div class="menu-card" onclick="openModal('withdraw-modal')">📤 Withdraw (/withdraw)</div>
                    <div class="menu-card" onclick="openModal('transfer-modal')">💸 Transfer (/transfer)</div>
                    <div class="menu-card" onclick="openSection('invite')">👥 Invite (/invite)</div>
                    <div class="menu-card" onclick="openModal('promo-modal')">🎁 Promo Code (/promo)</div>
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

            <!-- Stake Selection Modal -->
            <div id="stake-modal" class="modal">
                <h4 style="margin-top:0;">የመወራረጃ መጠን ይምረጡ (Stake)</h4>
                <div class="stake-opts">
                    <button class="stake-btn selected" id="stake-10" onclick="setStake(10)">10 ETB</button>
                    <button class="stake-btn" id="stake-20" onclick="setStake(20)">20 ETB</button>
                    <button class="stake-btn" id="stake-30" onclick="setStake(30)">30 ETB</button>
                </div>
                <button onclick="proceedToCartellaSelection()">ቀጥል (Select Cartella)</button>
                <button style="background:#e53935;" onclick="closeModal('stake-modal')">ተመለስ</button>
            </div>

            <script>
                const tg = window.Telegram.WebApp;
                tg.ready();
                tg.expand();

                const user = tg.initDataUnsafe?.user || { id: 12345678, first_name: "Demo User" };
                let currentStake = 10;

                fetch('/api/sync-user', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ telegram_id: user.id, first_name: user.first_name })
                }).then(res => res.json()).then(data => {
                    if(data.status === 'success'){
                        document.getElementById('user-display').innerText = data.user.first_name;
                        document.getElementById('main-balance').innerText = data.user.balance.toFixed(2);
                    }
                });

                function openModal(id) { document.getElementById(id).style.display = 'block'; }
                function closeModal(id) { document.getElementById(id).style.display = 'none'; }
                function setStake(amount) { currentStake = amount; }
                function proceedToCartellaSelection() { alert("ጨዋታው በቅርብ ይጀምራል!"); }

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
            </script>
        </body>
        </html>
    """)

# ==========================================
# USER SYNC & TRANSACTIONS
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

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))

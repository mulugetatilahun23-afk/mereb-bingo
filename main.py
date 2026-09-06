from flask import Flask, request, jsonify, render_template_string
import sqlite3
import os
import random

app = Flask(__name__)

# ዳታቤዝ ማዘጋጀት
def init_db():
    conn = sqlite3.connect('mereb_bingo.db')
    cursor = conn.cursor()
    
    # ተጠቃሚዎች
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            telegram_id INTEGER PRIMARY KEY,
            balance REAL DEFAULT 0.0,
            coins REAL DEFAULT 0.0,
            agent_id INTEGER
        )
    ''')
    
    # ኤጀንቶች
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS agents (
            agent_id INTEGER PRIMARY KEY,
            referral_code TEXT UNIQUE,
            commission_balance REAL DEFAULT 0.0
        )
    ''')
    
    # የገንዘብ ዝውውር (Deposit/Withdraw)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER,
            amount REAL,
            type TEXT,
            method TEXT,
            status TEXT DEFAULT 'pending'
        )
    ''')
    
    # የተመረጡ ካርዶች
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_cards (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER,
            stake REAL,
            card_data TEXT
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# የፊት ገጽ (UI) - ዳርክ ቲም እና የተስተካከሉ የባንክ መረጃዎች
@app.route('/')
def index():
    return render_template_string("""
    <!DOCTYPE html>
    <html lang="am">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Mereb Bingo</title>
        <style>
            body { background-color: #121212; color: #ffffff; font-family: sans-serif; text-align: center; margin: 0; padding: 15px; }
            h2 { color: #f39c12; }
            .box { background: #1e1e1e; padding: 12px; border-radius: 10px; margin-bottom: 15px; border: 1px solid #333; }
            .btn { background: #e67e22; color: white; border: none; padding: 10px 15px; border-radius: 5px; cursor: pointer; font-size: 14px; margin: 5px; }
            .btn:hover { background: #d35400; }
            .card-grid { display: grid; grid-template-columns: repeat(5, 1fr); gap: 4px; max-width: 280px; margin: 10px auto; background: #222; padding: 8px; border-radius: 8px; }
            .cell { background: #333; padding: 8px; font-size: 13px; border-radius: 4px; }
            input, select { padding: 8px; margin: 5px; border-radius: 5px; border: 1px solid #444; background: #222; color: white; width: 85%; }
            .payment-info { font-size: 13px; color: #3498db; background: #15202b; padding: 10px; border-radius: 5px; margin-top: 5px; text-align: left; line-height: 1.5; }
        </style>
    </head>
    <body>
        <h2>🎯 Mereb Bingo Mini App</h2>
        
        <div class="box">
            <p>ቀሪ ሂሳብ: <span id="balance">0.00</span> ብር | ኮይን: <span id="coins">0.0</span></p>
            <input type="number" id="userId" placeholder="የቴሌግራም ID ያስገቡ"><br>
            <button class="btn" onclick="loadAccount()">መረጃ አሳይ</button>
        </div>

        <div class="box">
            <h3>ገንዘብ ማስገባት / ማውጣት</h3>
            <div class="payment-info">
                <b>የክፍያ አካውንቶች:</b><br>
                • ቴሌብር: <b>0923410403</b> (ሙሉጌታ ጥላሁን)<br>
                • ንግድ ባንክ (CBE): <b>1000149356138</b> (ሙሉጌታ ጥላሁን)
            </div>
            <input type="number" id="amount" placeholder="የገንዘብ መጠን (ብር)"><br>
            <select id="method">
                <option value="Telebirr">ቴሌብር (Telebirr)</option>
                <option value="CBE">ንግድ ባንክ (CBE)</option>
            </select><br>
            <button class="btn" onclick="makeTransaction('deposit')">ገንዘብ ገቢ አድርግ (/deposit)</button>
            <button class="btn" onclick="makeTransaction('withdraw')" style="background: #c0392b;">ገንዘብ አውጣ (/withdraw)</button>
        </div>

        <div class="box">
            <h3>የጨዋታ ውርርድ (Play / 5x5)</h3>
            <p>ከ 1 እስከ 300 ቁጥሮች (እስከ 2 ካርድ)</p>
            <div>
                <button class="btn" onclick="generateCards(10)">10 ብር መጫወቻ</button>
                <button class="btn" onclick="generateCards(20)">20 ብር መጫወቻ</button>
                <button class="btn" onclick="generateCards(30)">30 ብር መጫወቻ</button>
            </div>
            <div id="cardsContainer"></div>
        </div>

        <script>
            function loadAccount() {
                const uid = document.getElementById('userId').value;
                if(!uid) return alert('እባክዎ መጀመሪያ የቴሌግራም ID ያስገቡ');
                fetch('/api/account/' + uid)
                .then(res => res.json())
                .then(data => {
                    document.getElementById('balance').innerText = data.balance;
                    document.getElementById('coins').innerText = data.coins;
                });
            }

            function makeTransaction(type) {
                const uid = document.getElementById('userId').value;
                const amount = document.getElementById('amount').value;
                const method = document.getElementById('method').value;
                if(!uid || !amount) return alert('ሁሉንም መረጃዎች ይሙሉ');

                fetch('/api/' + type, {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({telegram_id: parseInt(uid), amount: parseFloat(amount), method: method})
                })
                .then(res => res.json())
                .then(data => {
                    alert(data.message);
                    loadAccount();
                });
            }

            function generateCards(stake) {
                const uid = document.getElementById('userId').value;
                if(!uid) return alert('እባክዎ መጀመሪያ የቴሌግራም ID ያስገቡ');

                fetch('/api/generate-cards', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({telegram_id: parseInt(uid), stake: stake})
                })
                .then(res => res.json())
                .then(data => {
                    if(data.status === 'success') {
                        alert(data.message);
                        let html = '';
                        data.cards.forEach((card, index) => {
                            html += `<h4>ካርድ ${index + 1}</h4><div class="card-grid">`;
                            card.forEach(num => {
                                html += `<div class="cell">${num}</div>`;
                            });
                            html += `</div>`;
                        });
                        document.getElementById('cardsContainer').innerHTML = html;
                        loadAccount();
                    } else {
                        alert(data.message);
                    }
                });
            }
        </script>
    </body>
    </html>
    """)

# የሂሳብ እና ኮይን መረጃ ማሳያ
@app.route('/api/account/<int:telegram_id>')
def get_account(telegram_id):
    conn = sqlite3.connect('mereb_bingo.db')
    cursor = conn.cursor()
    cursor.execute("SELECT balance, coins FROM users WHERE telegram_id = ?", (telegram_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return jsonify({"balance": row[0], "coins": row[1]})
    return jsonify({"balance": 0.0, "coins": 0.0})

# ገንዘብ ገቢ ማድረግ (/deposit)
@app.route('/api/deposit', methods=['POST'])
def deposit():
    data = request.json
    telegram_id = data.get('telegram_id')
    amount = data.get('amount')
    method = data.get('method')
    
    conn = sqlite3.connect('mereb_bingo.db')
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO users (telegram_id, balance, coins) VALUES (?, 0.0, 0.0)", (telegram_id,))
    cursor.execute("INSERT INTO transactions (telegram_id, amount, type, method) VALUES (?, ?, 'deposit', ?)",
                 (telegram_id, amount, method))
    cursor.execute("UPDATE users SET balance = balance + ? WHERE telegram_id = ?", (amount, telegram_id))
    conn.commit()
    conn.close()
    
    return jsonify({"status": "success", "message": f"{amount} ብር በ {method} የገቢ ጥያቄ ተመዝግቧል!"})

# ገንዘብ ማውጣት (/withdraw)
@app.route('/api/withdraw', methods=['POST'])
def withdraw():
    data = request.json
    telegram_id = data.get('telegram_id')
    amount = data.get('amount')
    method = data.get('method')
    
    conn = sqlite3.connect('mereb_bingo.db')
    cursor = conn.cursor()
    cursor.execute("SELECT balance FROM users WHERE telegram_id = ?", (telegram_id,))
    row = cursor.fetchone()
    
    if not row or row[0] < amount:
        conn.close()
        return jsonify({"status": "error", "message": "በቂ ቀሪ ሂሳብ የለዎትም!"})
        
    cursor.execute("UPDATE users SET balance = balance - ? WHERE telegram_id = ?", (amount, telegram_id))
    cursor.execute("INSERT INTO transactions (telegram_id, amount, type, method) VALUES (?, ?, 'withdraw', ?)",
                 (telegram_id, amount, method))
    conn.commit()
    conn.close()
    
    return jsonify({"status": "success", "message": f"{amount} ብር የማውጣት ጥያቄ ተልኳል!"})

# 5x5 ካርዶችን ማመንጨት (1 እስከ 300, 2 ካርድ ገደብ, 20% ባለቤት, 5% ኤጀንት)
@app.route('/api/generate-cards', methods=['POST'])
def generate_cards():
    data = request.json
    telegram_id = data.get('telegram_id')
    stake = data.get('stake') # 10, 20, 30 ብር
    total_cost = stake * 2 # 2 ካርዶች
    
    conn = sqlite3.connect('mereb_bingo.db')
    cursor = conn.cursor()
    
    cursor.execute("SELECT balance, agent_id FROM users WHERE telegram_id = ?", (telegram_id,))
    user = cursor.fetchone()
    
    if not user or user[0] < total_cost:
        conn.close()
        return jsonify({"status": "error", "message": "ለ 2 ካርዶች የሚሆን በቂ ቀሪ ሂሳብ የለዎትም!"})
        
    agent_id = user[1]
    
    cursor.execute("UPDATE users SET balance = balance - ? WHERE telegram_id = ?", (total_cost, telegram_id))
    
    cards = []
    for _ in range(2):
        card_numbers = random.sample(range(1, 301), 25)
        cards.append(card_numbers)
        cursor.execute("INSERT INTO user_cards (telegram_id, stake, card_data) VALUES (?, ?, ?)",
                     (telegram_id, stake, str(card_numbers)))

    # ኮሚሽን ስሌት (20% ለባለቤት፣ 5% ለኤጀንት)
    platform_cut = total_cost * 0.20
    agent_cut = (total_cost * 0.05) if agent_id else 0.0
    
    if agent_id:
        cursor.execute("UPDATE agents SET commission_balance = commission_balance + ? WHERE agent_id = ?",
                     (agent_cut, agent_id))

    conn.commit()
    conn.close()
    
    return jsonify({
        "status": "success", 
        "message": f"2 ካርዶች ተመርጠዋል! (ድርሻ: ባለቤት 20%, ኤጀንት 5%)",
        "cards": cards
    })

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)

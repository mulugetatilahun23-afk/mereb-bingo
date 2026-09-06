from flask import Flask, request, jsonify, render_template_string
import sqlite3
import os
import random

app = Flask(__name__)

# ዳታቤዝ ማዘጋጀት
def init_db():
    conn = sqlite3.connect('mereb_bingo.db')
    cursor = conn.cursor()
    
    # ተጠቃሚዎች (Main Wallet, Commission, Phone, Language)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            telegram_id INTEGER PRIMARY KEY,
            phone_number TEXT,
            balance REAL DEFAULT 0.0,
            commission_balance REAL DEFAULT 0.0,
            coins REAL DEFAULT 0.0,
            agent_id INTEGER,
            language TEXT DEFAULT 'am'
        )
    ''')
    
    # ኤጀንቶች እና ሪፈራል
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS agents (
            agent_id INTEGER PRIMARY KEY,
            telegram_id INTEGER,
            referral_code TEXT UNIQUE,
            commission_balance REAL DEFAULT 0.0
        )
    ''')
    
    # የገንዘብ ዝውውር (Deposit/Withdraw/Transfer)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER,
            amount REAL,
            type TEXT,
            method TEXT,
            status TEXT DEFAULT 'pending',
            date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # ፕሮሞ ኮዶች
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS promo_codes (
            code TEXT PRIMARY KEY,
            reward REAL,
            used INTEGER DEFAULT 0
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# የፊት ገጽ (UI) - ሙሉ ሎጂክ እና ንድፍ
@app.route('/')
def index():
    return render_template_string("""
    <!DOCTYPE html>
    <html lang="am">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Mereb Bingo Mini App</title>
        <style>
            body { background-color: #121212; color: #ffffff; font-family: sans-serif; text-align: center; margin: 0; padding: 10px; }
            h2 { color: #f39c12; font-size: 20px; }
            .box { background: #1e1e1e; padding: 12px; border-radius: 8px; margin-bottom: 12px; border: 1px solid #333; text-align: left; }
            .btn { background: #e67e22; color: white; border: none; padding: 10px; border-radius: 5px; cursor: pointer; font-size: 14px; margin: 4px 0; width: 100%; }
            .btn:hover { background: #d35400; }
            .card-grid { display: grid; grid-template-columns: repeat(5, 1fr); gap: 4px; max-width: 280px; margin: 10px auto; background: #222; padding: 8px; border-radius: 6px; }
            .cell { background: #333; padding: 8px; font-size: 13px; border-radius: 4px; text-align: center; }
            .marked { background: #27ae60 !important; color: white; font-weight: bold; }
            input, select { padding: 9px; margin: 5px 0; border-radius: 5px; border: 1px solid #444; background: #222; color: white; width: 100%; box-sizing: border-box; }
            .info-box { font-size: 13px; color: #3498db; background: #15202b; padding: 10px; border-radius: 5px; margin-bottom: 8px; line-height: 1.5; }
            .copy-btn { background: #2980b9; padding: 5px 10px; font-size: 12px; width: auto; display: inline-block; margin-top: 5px; }
            .timer { color: #e74c3c; font-weight: bold; font-size: 16px; text-align: center; margin: 10px 0; }
        </style>
    </head>
    <body>
        <h2>🎯 Mereb Bingo Mini App</h2>
        
        <!-- Start / Registration -->
        <div class="box">
            <h3>1. /start & ምዝገባ</h3>
            <p style="font-size:12px; color:#aaa;">እንኳን ወደ መረብ ቢንጎ በደህና መጡ!</p>
            <input type="number" id="userId" placeholder="የቴሌግራም ID ያስገቡ">
            <input type="text" id="phone" placeholder="ስልክ ቁጥር (ለምሳሌ 0923... ወይም 07...)">
            <button class="btn" onclick="registerUser()">ስልክ ቁጥር Share አድርግ & ምዝገባ</button>
        </div>

        <!-- Balance (Main & Commission) -->
        <div class="box">
            <h3>3. /balance (ዋና እና ኮሚሽን ዋሌት)</h3>
            <button class="btn" onclick="loadAccount()">ሂሳብ አሳይ</button>
            <p style="font-size:14px;">Main Balance: <span id="balance" style="color:#2ecc71;">0.00</span> ብር</p>
            <p style="font-size:14px;">Commission Balance: <span id="commBalance" style="color:#f1c40f;">0.00</span> ብር</p>
        </div>

        <!-- Deposit -->
        <div class="box">
            <h3>4. /deposit (ገንዘብ ገቢ ማድረግ)</h3>
            <div class="info-box" id="paymentDetails">
                <b>የክፍያ አማራጮች:</b><br>
                • ቴሌብር: <span id="teleNum">0923410403</span> (ሙሉጌታ ጥላሁን) <button class="btn copy-btn" onclick="copyText('0923410403')">ኮፒ</button><br>
                • ንግድ ባንክ (CBE): <span id="cbeNum">1000149356138</span> (ሙሉጌታ ጥላሁን) <button class="btn copy-btn" onclick="copyText('1000149356138')">ኮፒ</button>
            </div>
            <input type="number" id="depAmount" placeholder="የገንዘብ መጠን (ብር)">
            <select id="depMethod">
                <option value="Telebirr">ቴሌብር (Telebirr)</option>
                <option value="CBE">ንግድ ባንክ (CBE)</option>
            </select>
            <input type="text" id="smsText" placeholder="የባንክ/ቴሌብር የክፍያ SMS መልእክት እዚህ ይለጥፉ (Paste)">
            <button class="btn" onclick="makeDeposit()">ክፍያ አረጋግጥና ሐዋላ አስገባ</button>
        </div>

        <!-- Withdraw -->
        <div class="box">
            <h3>5. /withdraw (ገንዘብ ማውጣት)</h3>
            <p style="font-size:11px; color:#e67e22;">ማስታወሻ፡ 50 ብር ቀሪ መኖር አለበት። በቀን ከፍተኛው ውጭ 2000 ብር ነው።</p>
            <input type="number" id="withAmount" placeholder="የሚወጣው መጠን (ብር)">
            <select id="withMethod">
                <option value="Telebirr">ቴሌብር</option>
                <option value="CBE">ንግድ ባንክ</option>
            </select>
            <input type="text" id="withAccount" placeholder="የመቀበያ ስልክ ወይም አካውንት ቁጥር">
            <button class="btn" style="background: #c0392b;" onclick="makeWithdraw()">ገንዘብ አውጣ</button>
        </div>

        <!-- Play / 5x5 -->
        <div class="box">
            <h3>2. /play (ጨዋታ መጀመር)</h3>
            <select id="stake">
                <option value="10">10 ብር (1-300 ካርቴላ)</option>
                <option value="20">20 ብር (1-300 ካርቴላ)</option>
                <option value="30">30 ብር (1-300 ካርቴላ)</option>
                <option value="group">Group Play</option>
            </select>
            <button class="btn" onclick="startPlay()">ካርቴላ አስመርጥ & ቆጣሪ ጀምር</button>
            <div class="timer" id="timerDisplay"></div>
            <div id="gameArea"></div>
        </div>

        <!-- Transfer to User -->
        <div class="box">
            <h3>9. /transfer (ለሌላ ተጠቃሚ ማስተላለፍ)</h3>
            <p style="font-size:11px; color:#aaa;">ዝቅተኛው የዝውውር መጠን 10 ብር ነው።</p>
            <input type="text" id="targetPhone" placeholder="የተቀባይ ስልክ ቁጥር">
            <input type="number" id="transAmount" placeholder="የገንዘብ መጠን (ብር)">
            <button class="btn" onclick="transferMoney()">ገንዘብ አስተላልፍ</button>
        </div>

        <!-- Other Commands -->
        <div class="box">
            <h3>ማውጫ እና መቆጣጠሪያዎች</h3>
            <button class="btn" onclick="showLeaderboard()">6. /leaderboard - ኤጀንት ፕሮፋይል</button>
            <button class="btn" onclick="showInstruction()">7. /instruction - የጨዋታ ህግ</button>
            <button class="btn" onclick="generateInvite()">8. /invite - ሪፈራል ሊንክ</button>
            <input type="text" id="promoCode" placeholder="ፕሮሞ ኮድ">
            <button class="btn" onclick="redeemPromo()">/promo - ኮድ መጠቀም</button>
            <button class="btn" onclick="showSupport()">10. /support - የቴሌግራም ቻናል</button>
            <select id="langSelect" onchange="changeLanguage()">
                <option value="am">11. አማርኛ (Amharic)</option>
                <option value="en">11. English</option>
            </select>
        </div>

        <script>
            function copyText(text) {
                navigator.clipboard.writeText(text);
                alert("ተገለበጠ (Copied): " + text);
            }

            function registerUser() {
                const uid = document.getElementById('userId').value;
                const phone = document.getElementById('phone').value;
                if(!uid || !phone) return alert('እባክዎ ID እና ስልክ ቁጥር ያስገቡ');

                fetch('/api/register', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({telegram_id: parseInt(uid), phone_number: phone})
                })
                .then(res => res.json())
                .then(data => alert(data.message));
            }

            function loadAccount() {
                const uid = document.getElementById('userId').value;
                if(!uid) return alert('እባክዎ መጀመሪያ ID ያስገቡ');
                fetch('/api/account/' + uid)
                .then(res => res.json())
                .then(data => {
                    document.getElementById('balance').innerText = data.balance;
                    document.getElementById('commBalance').innerText = data.commission_balance;
                });
            }

            function makeDeposit() {
                const uid = document.getElementById('userId').value;
                const amount = document.getElementById('depAmount').value;
                const method = document.getElementById('depMethod').value;
                const sms = document.getElementById('smsText').value;
                if(!uid || !amount) return alert('እባክዎ ID እና መጠን ይሙሉ');

                fetch('/api/deposit', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({telegram_id: parseInt(uid), amount: parseFloat(amount), method: method, sms_text: sms})
                })
                .then(res => res.json())
                .then(data => alert(data.message));
            }

            function makeWithdraw() {
                const uid = document.getElementById('userId').value;
                const amount = document.getElementById('withAmount').value;
                const method = document.getElementById('withMethod').value;
                const acc = document.getElementById('withAccount').value;
                if(!uid || !amount || !acc) return alert('ሁሉንም መረጃዎች ይሙሉ');

                fetch('/api/withdraw', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({telegram_id: parseInt(uid), amount: parseFloat(amount), method: method, account: acc})
                })
                .then(res => res.json())
                .then(data => alert(data.message));
            }

            function startPlay() {
                const uid = document.getElementById('userId').value;
                const stake = document.getElementById('stake').value;
                if(!uid) return alert('እባክዎ መጀመሪያ ID ያስገቡ');

                let timeLeft = 30;
                const timerElem = document.getElementById('timerDisplay');
                document.getElementById('gameArea').innerHTML = "<p>ካርቴላ በመዘጋጀት ላይ...</p>";

                let timerInterval = setInterval(() => {
                    timerElem.innerText = `⏳ ጨዋታ ለመጀመር የቀረው ጊዜ: ${timeLeft} ሰከንድ`;
                    timeLeft--;
                    if(timeLeft < 0) {
                        clearInterval(timerInterval);
                        timerElem.innerText = "🎮 ጨዋታው ተጀምሯል! ቁጥሮች እየተጠሩ ነው...";
                        fetchAndRunGame(uid, stake);
                    }
                }, 1000);
            }

            function fetchAndRunGame(uid, stake) {
                fetch('/api/play', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({telegram_id: parseInt(uid), stake: stake})
                })
                .then(res => res.json())
                .then(data => {
                    if(data.status === 'success') {
                        let html = `<h4>የተመረጠው ካርቴላ (5x5)</h4><div class="card-grid" id="cardGrid">`;
                        data.card.forEach(num => {
                            html += `<div class="cell" id="cell-${num}">${num}</div>`;
                        });
                        html += `</div><p id="callStatus" style="color:#f1c40f; font-weight:bold;"></p>`;
                        document.getElementById('gameArea').innerHTML = html;

                        // አውቶማቲክ የቁጥር ጥሪ እና አሸናፊ ማሳያ
                        simulateBingoCaller(data.card);
                    } else {
                        alert(data.message);
                    }
                });
            }

            function simulateBingoCaller(cardNumbers) {
                let calledCount = 0;
                let interval = setInterval(() => {
                    if(calledCount >= 10 || cardNumbers.length === 0) {
                        clearInterval(interval);
                        document.getElementById('callStatus').innerText = "🎉 ቢያንጎ! (BINGO)! ተጫዋቹ አሸንፏል! ሽልማቱ ወደ Main Wallet ገብቷል!";
                        loadAccount();
                        return;
                    }
                    let randomCalledNum = cardNumbers[Math.floor(Math.random() * cardNumbers.length)];
                    document.getElementById('callStatus').innerText = `🔊 የተጠራ ቁጥር: ${randomCalledNum}`;
                    let cell = document.getElementById('cell-' + randomCalledNum);
                    if(cell) cell.classList.add('marked');
                    calledCount++;
                }, 2000);
            }

            function transferMoney() {
                const uid = document.getElementById('userId').value;
                const phone = document.getElementById('targetPhone').value;
                const amount = document.getElementById('transAmount').value;
                if(!uid || !phone || !amount) return alert('መረጃዎችን በትክክል ይሙሉ');

                fetch('/api/transfer', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({telegram_id: parseInt(uid), target_phone: phone, amount: parseFloat(amount)})
                })
                .then(res => res.json())
                .then(data => alert(data.message));
            }

            function showLeaderboard() {
                const uid = document.getElementById('userId').value;
                if(!uid) return alert('እባክዎ ID ያስገቡ');
                fetch('/api/agent-profile/' + uid)
                .then(res => res.json())
                .then(data => {
                    alert(`🏆 ኤጀንት ፕሮፋይል\\n- ኤጀንት ID: ${data.agent_id}\\n- ሪፈራል ኮድ: ${data.code}\\n- የተጠራቀመ ኮሚሽን: ${data.comm} ብር`);
                });
            }

            function showInstruction() {
                alert("📜 የጨዋታ ህግ:\\n1. ከ 1 እስከ 300 ያሉ ቁጥሮች በ 5x5 ግሪድ ይጫወታሉ።\\n2. ካርቴላ ከመረጡ በኋላ የ 30 ሰከንድ ቆጣሪ ይጠበቃል።\\n3. ሲስተሙ በራሱ ቁጥሮችን እየጠራ ያሰምራል።\\n4. ቢያንጎ ሲባል ሽልማቱ በቀጥታ ወደ Main Wallet ይገባል።");
            }

            function generateInvite() {
                const uid = document.getElementById('userId').value;
                if(!uid) return alert('እባክዎ ID ያስገቡ');
                alert("🔗 የእርስዎ ሪፈራል ሊንክ:\\nhttps://t.me/MerebBingoBot?start=agent_" + uid);
            }

            function redeemPromo() {
                const uid = document.getElementById('userId').value;
                const code = document.getElementById('promoCode').value;
                if(!uid || !code) return alert('እባክዎ ID እና ኮድ ይሙሉ');
                fetch('/api/promo', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({telegram_id: parseInt(uid), code: code})
                })
                .then(res => res.json())
                .then(data => alert(data.message));
            }

            function showSupport() {
                alert("💬 የድጋፍ ማዕከል:\\nየቴሌግራም ቻናል: @support_merebbingo\\nአስተዳዳሪ: @MulugetaTilahun (ስልክ: 0923410403)");
            }

            function changeLanguage() {
                const lang = document.getElementById('langSelect').value;
                alert("ቋንቋው ወደ " + (lang === 'am' ? 'አማርኛ' : 'English') + " ተቀይሯል!");
            }
        </script>
    </body>
    </html>
    """)

# ኤፒአይ ሎጂኮች
@app.route('/api/register', methods=['POST'])
def register():
    data = request.json
    telegram_id = data.get('telegram_id')
    phone = data.get('phone_number')
    conn = sqlite3.connect('mereb_bingo.db')
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO users (telegram_id, phone_number, balance, commission_balance) VALUES (?, ?, COALESCE((SELECT balance FROM users WHERE telegram_id = ?), 0.0), COALESCE((SELECT commission_balance FROM users WHERE telegram_id = ?), 0.0))", 
                   (telegram_id, phone, telegram_id, telegram_id))
    conn.commit()
    conn.close()
    return jsonify({"status": "success", "message": "በተሳካ ሁኔታ ተመዝግበዋል! ስልክ ቁጥርዎ ተይዟል።"})

@app.route('/api/account/<int:telegram_id>')
def get_account(telegram_id):
    conn = sqlite3.connect('mereb_bingo.db')
    cursor = conn.cursor()
    cursor.execute("SELECT balance, commission_balance FROM users WHERE telegram_id = ?", (telegram_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return jsonify({"balance": row[0], "commission_balance": row[1]})
    return jsonify({"balance": 0.0, "commission_balance": 0.0})

@app.route('/api/deposit', methods=['POST'])
def deposit():
    data = request.json
    telegram_id = data.get('telegram_id')
    amount = data.get('amount')
    method = data.get('method')
    sms = data.get('sms_text', '')
    
    conn = sqlite3.connect('mereb_bingo.db')
    cursor = conn.cursor()
    cursor.execute("INSERT INTO transactions (telegram_id, amount, type, method, status) VALUES (?, ?, 'deposit', ?, 'approved')",
                 (telegram_id, amount, method))
    cursor.execute("UPDATE users SET balance = balance + ? WHERE telegram_id = ?", (amount, telegram_id))
    conn.commit()
    conn.close()
    return jsonify({"status": "success", "message": f"ክፍያው ተረጋግጧል! {amount} ብር ወደ Main Wallet ገብቷል።"})

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
    
    if not row or (row[0] - amount) < 50:
        conn.close()
        return jsonify({"status": "error", "message": "ውድቅ ተደርጓል! ቢያንስ 50 ብር አካውንትዎ ላይ ሊቀር ይገባል።"})
        
    if amount > 2000:
        conn.close()
        return jsonify({"status": "error", "message": "በ 24 ሰአት ውስጥ ማውጣት የሚችሉት ከፍተኛው መጠን 2000 ብር ብቻ ነው።"})
        
    cursor.execute("UPDATE users SET balance = balance - ? WHERE telegram_id = ?", (amount, telegram_id))
    cursor.execute("INSERT INTO transactions (telegram_id, amount, type, method, status) VALUES (?, ?, 'withdraw', ?, 'approved')",
                 (telegram_id, amount, method))
    conn.commit()
    conn.close()
    return jsonify({"status": "success", "message": f"{amount} ብር የማውጣት ጥያቄ ተሳክቷል!"})

@app.route('/api/play', methods=['POST'])
def play():
    data = request.json
    telegram_id = data.get('telegram_id')
    stake = data.get('stake')
    
    cost = 10 if stake == '10' else (20 if stake == '20' else (30 if stake == '30' else 50))
    
    conn = sqlite3.connect('mereb_bingo.db')
    cursor = conn.cursor()
    cursor.execute("SELECT balance FROM users WHERE telegram_id = ?", (telegram_id,))
    row = cursor.fetchone()
    
    if not row or row[0] < cost:
        conn.close()
        return jsonify({"status": "error", "message": "በቂ ቀሪ ሂሳብ የለዎትም!"})
        
    # ዋጋ መቀነስ እና ሽልማቱን መልሶ ማስገባት (Simulation)
    cursor.execute("UPDATE users SET balance = balance - ? WHERE telegram_id = ?", (cost, telegram_id))
    prize = cost * 2 # አሸናፊ ሲሆን የሚገባው
    cursor.execute("UPDATE users SET balance = balance + ? WHERE telegram_id = ?", (prize, telegram_id))
    conn.commit()
    conn.close()
    
    card_numbers = random.sample(range(1, 301), 25)
    return jsonify({"status": "success", "card": card_numbers, "message": "ጨዋታ ተጀምሯል!"})

@app.route('/api/transfer', methods=['POST'])
def transfer():
    data = request.json
    telegram_id = data.get('telegram_id')
    target_phone = data.get('target_phone')
    amount = data.get('amount')
    
    if amount < 10:
        return jsonify({"status": "error", "message": "ዝቅተኛው የዝውውር መጠን 10 ብር ነው።"})
        
    conn = sqlite3.connect('mereb_bingo.db')
    cursor = conn.cursor()
    cursor.execute("SELECT balance FROM users WHERE telegram_id = ?", (telegram_id,))
    sender = cursor.fetchone()
    
    if not sender or sender[0] < amount:
        conn.close()
        return jsonify({"status": "error", "message": "በቂ ቀሪ ሂሳብ የለዎትም!"})
        
    cursor.execute("SELECT telegram_id FROM users WHERE phone_number = ?", (target_phone,))
    receiver = cursor.fetchone()
    
    if not receiver:
        conn.close()
        return jsonify({"status": "error", "message": "የተቀባይ ስልክ ቁጥር አልተገኘም!"})
        
    cursor.execute("UPDATE users SET balance = balance - ? WHERE telegram_id = ?", (amount, telegram_id))
    cursor.execute("UPDATE users SET balance = balance + ? WHERE telegram_id = ?", (amount, receiver[0]))
    conn.commit()
    conn.close()
    return jsonify({"status": "success", "message": f"{amount} ብር በተሳካ ሁኔታ ተላልፏል!"})

@app.route('/api/agent-profile/<int:telegram_id>')
def agent_profile(telegram_id):
    conn = sqlite3.connect('mereb_bingo.db')
    cursor = conn.cursor()
    cursor.execute("SELECT commission_balance FROM users WHERE telegram_id = ?", (telegram_id,))
    row = cursor.fetchone()
    conn.close()
    comm = row[0] if row else 0.0
    return jsonify({"agent_id": telegram_id, "code": f"agent_{telegram_id}", "comm": comm})

@app.route('/api/promo', methods=['POST'])
def promo():
    data = request.json
    telegram_id = data.get('telegram_id')
    code = data.get('code')
    return jsonify({"status": "success", "message": "ፕሮሞ ኮዱ ተቀባይነት አግኝቷል!"})

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
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

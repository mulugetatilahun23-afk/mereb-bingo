from flask import Flask, request, jsonify, render_template_string
import sqlite3
import os
import random
import json
import re
import urllib.parse
from datetime import datetime

app = Flask(name)

Environment Variables
BOT_TOKEN = os.environ.get(" ", "")
BOT_USERNAME = os.environ.get("BOT_USERNAME", "MerebBingoBot")
DB_NAME = 'mereb_bingo.db'

MERCHANT_PHONE = "0923410403"
MERCHANT_NAME = "MULUGETA TILAHUN"
REFERRAL_BONUS = 5.0
DAILY_LIMIT = 2000.0 # በቀን የሚፈቀድ ከፍተኛ ወጪ/ትራንስፈር
MIN_REMAINING_BALANCE = 50.0 # በቀሪነት መቅረት ያለበት ዝቅተኛ ባላንስ
COMMISSION_RATE = 0.20 # 20% የሲስተም ኮሚሽን

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
agent_id INTEGER
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
status TEXT DEFAULT 'approved',
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
used INTEGER DEFAULT 0
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

@app.route('/health', methods=['GET'])
def health():
return jsonify({"status": "alive", "project": "Mereb Bingo"}), 200

==========================================
FRONTEND MINI APP
==========================================
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
.bingo-cell.marked { background: #ffb300; color: #000; }
.bingo-cell.drawn-green { background: #00c853; color: #fff; }

.winner-banner { background: linear-gradient(135deg, #1e3c72, #2a5298); padding: 12px; border-radius: 10px; text-align: center; margin-bottom: 15px; border: 1px solid #ffb300; }
</style>
</head>
<body>

<!-- Home Dashboard -->
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
<div class="menu-card" onclick="openSection('leaderboard')">🏆 Leaderboard</div>
<div class="menu-card" onclick="openSection('support')">💬 Support</div>
</div>
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

<!-- Cartella Selection View (1-300) -->
<div id="cartella-view" class="page-view">
<div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px;">
<button style="width:auto; margin:0; padding:6px 12px;" onclick="exitCartellaView()">← Back</button>
<span><b>Select Your Cartella</b> (1-300)</span>
</div>

<div class="cartella-header">
<div>TIMER<br><b id="timer-val" style="color:#ff5252;">30</b></div>
<div>DERASH<br><b id="derash-val">0.00</b> ETB</div>
<div>STAKE<br><b id="disp-stake">10</b> ETB</div>
<div>PLAYERS<br><b id="players-val">1</b></div>
</div>

<div class="cartella-grid" id="cartella-container">
<!-- 1 to 300 Buttons -->
</div>
<button style="margin-top:12px;" onclick="confirmCartellaSelection()">ካርቴላ አረጋግጥ (Join Game)</button>
</div>

<!-- Active Bingo Game View -->
<div id="game-view" class="page-view">
<div class="winner-banner" id="winner-box">
<h3 style="margin:0; color:#ffb300;">🎉🏆🎉 BINGO!</h3>
<p style="margin:5px 0 0 0;" id="winner-text">Game in Progress...</p>
</div>

<div class="bingo-card">
<div style="display:flex; justify-content:space-between; font-size:12px; color:#aaa; margin-bottom:5px;">
<span id="card-title">Cartella #--</span>
<span id="player-owner">Owner: You</span>
</div>

<div class="bingo-grid" id="bingo-board">
<!-- 5x5 Grid -->
</div>
</div>

<div style="text-align:center; margin-top:20px;">
<button style="width:auto; padding:10px 20px; background:#00c853;" onclick="claimBingo()">🔥 BINGO! (Claim Win)</button>
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
<h4>ገንዘብ ማውጫ (Withdraw)</h4>
<p style="font-size: 11px; color: #aaa;">* በቀን እስከ 2000 ETB ብቻ ማውጣት ይቻላል። 50 ETB በቀሪነት መቅረት አለበት።</p>
<input type="text" id="withdraw-phone" placeholder="የቴሌብር ስልክ ቁጥር (09...)">
<input type="number" id="withdraw-amount" placeholder="የሚወጣው ብር መጠን">
<button onclick="submitWithdraw()">ወጪ አድርግ (Withdraw)</button>
<button style="background:#e53935;" onclick="closeModal('withdraw-modal')">ዝጋ</button>
</div>

<!-- Transfer Modal -->
<div id="transfer-modal" class="modal">
<h4>Transfer Money</h4>
<p style="font-size: 11px; color: #aaa;">* በቀን እስከ 2000 ETB ብቻ። 50 ETB በቀሪነት መቅረት አለበት።</p>
<input type="text" id="transfer-receiver" placeholder="የተቀባይ Telegram ID ወይም ስልክ">
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
let currentStake = 10;
let selectedCartella = null;
let timerInterval = null;
let currentCardData = null;

// Sync User Profile
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

function showView(viewId) {
document.querySelectorAll('.page-view').forEach(el => el.classList.remove('active-view'));
document.getElementById(viewId).classList.add('active-view');
}

function openModal(id) { document.getElementById(id).style.display = 'block'; }
function closeModal(id) { document.getElementById(id).style.display = 'none'; }

function setStake(amount) {
currentStake = amount;
document.querySelectorAll('.stake-btn').forEach(btn => btn.classList.remove('selected'));
document.getElementById('stake-' + amount).classList.add('selected');
}

function proceedToCartellaSelection() {
closeModal('stake-modal');
document.getElementById('disp-stake').innerText = currentStake;
render300Cartellas();
fetchGameStats();
start30SecTimer();
showView('cartella-view');
}

function start30SecTimer() {
let timeLeft = 30;
document.getElementById('timer-val').innerText = timeLeft;
if(timerInterval) clearInterval(timerInterval);

timerInterval = setInterval(() => {
timeLeft--;
document.getElementById('timer-val').innerText = timeLeft;
if(timeLeft <= 0) {
clearInterval(timerInterval);
alert("የምርጫ ጊዜ አልቋል! እባክዎን እንደገና ይሞክሩ።");
showView('home-view');
}
}, 1000);
}

function exitCartellaView() {
if(timerInterval) clearInterval(timerInterval);
showView('home-view');
}

function fetchGameStats() {
fetch('/api/game/stats?stake=' + currentStake)
.then(r => r.json())
.then(res => {
document.getElementById('players-val').innerText = res.players;
document.getElementById('derash-val').innerText = res.derash.toFixed(2);
});
}

function render300Cartellas() {
const container = document.getElementById('cartella-container');
container.innerHTML = '';
for (let i = 1; i <= 300; i++) {
const div = document.createElement('div');
div.className = 'cartella-num' + (selectedCartella === i ? ' selected' : '');
div.innerText = i;
div.onclick = () => { selectedCartella = i; render300Cartellas(); };
container.appendChild(div);
}
}

function confirmCartellaSelection() {
if (!selectedCartella) return alert("እባክዎን 1 ካርቴላ ይምረጡ!");

fetch('/api/game/generate-card', {
method: 'POST',
headers: { 'Content-Type': 'application/json' },
body: JSON.stringify({ telegram_id: user.id, cartella_num: selectedCartella, stake: currentStake })
}).then(r => r.json()).then(res => {
if (res.status === 'success') {
if(timerInterval) clearInterval(timerInterval);
currentCardData = res.card;
renderBingoBoard(res.card, selectedCartella);
showView('game-view');
} else {
alert(res.error || "ስህተት ተከሰተ!");
}
});
}

function renderBingoBoard(cardData, cartellaNum) {
document.getElementById('card-title').innerText = "Cartella #" + cartellaNum;
const board = document.getElementById('bingo-board');
board.innerHTML = '';

const headers = ['B', 'I', 'N', 'G', 'O'];
headers.forEach(h => {
const cell = document.createElement('div');
cell.className = 'bingo-cell header-cell';
cell.innerText = h;
board.appendChild(cell);
});

for (let row = 0; row < 5; row++) {
headers.forEach(col => {
const val = cardData[col][row];
const cell = document.createElement('div');

if (val === '★' || val === 'FREE') {
cell.className = 'bingo-cell star-cell';
cell.innerText = '★';
} else {
cell.className = 'bingo-cell';
cell.innerText = val;
}
board.appendChild(cell);
});
}
}

function claimBingo() {
fetch('/api/game/claim-bingo', {
method: 'POST',
headers: { 'Content-Type': 'application/json' },
body: JSON.stringify({ telegram_id: user.id, stake: currentStake })
}).then(r => r.json()).then(res => {
alert(res.message || res.error);
if(res.status === 'success') {
document.getElementById('winner-text').innerText = user.first_name + " won " + res.reward + " ETB!";
}
});
}

function openSection(type) {
if (type === 'support') {
tg.openTelegramLink('https://t.me/merebbingosupport');
} else if (type === 'invite') {
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

function submitWithdraw() {
const phone = document.getElementById('withdraw-phone').value;
const amount = parseFloat(document.getElementById('withdraw-amount').value);

fetch('/api/withdraw', {
method: 'POST',
headers: { 'Content-Type': 'application/json' },
body: JSON.stringify({ telegram_id: user.id, phone: phone, amount: amount })
}).then(r => r.json()).then(res => {
alert(res.message || res.error);
if(res.status === 'success') location.reload();
});
}

function submitTransfer() {
const receiver = document.getElementById('transfer-receiver').value;
const amount = parseFloat(document.getElementById('transfer-amount').value);

fetch('/api/transfer', {
method: 'POST',
headers: { 'Content-Type': 'application/json' },
body: JSON.stringify({ sender_id: user.id, receiver: receiver, amount: amount })
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

==========================================
USER SYNC
==========================================
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

==========================================
GAME STATS (PLAYERS & DERASH CALCULATOR)
==========================================
@app.route('/api/game/stats', methods=['GET'])
def game_stats():
stake = float(request.args.get('stake', 10.0))
conn = get_db()
cursor = conn.cursor()

# የዚሁ ውርርድ ተሳታፊዎችን ብዛት መቁጠር
player_count = cursor.execute('SELECT COUNT(DISTINCT telegram_id) as count FROM user_cards WHERE stake = ?', (stake,)).fetchone()['count']
if player_count == 0:
player_count = 1 # Default current player

# ደራሽ ስሌት = Total Stakes - 20% Commission
total_pot = player_count * stake
derash = total_pot * (1.0 - COMMISSION_RATE)

conn.close()
return jsonify({"players": player_count, "derash": derash, "stake": stake})

==========================================
GENERATE BINGO CARD
==========================================
@app.route('/api/game/generate-card', methods=['POST'])
def generate_card():
data = request.json or {}
telegram_id = data.get('telegram_id')
cartella_num = data.get('cartella_num')
stake = float(data.get('stake', 10.0))

if not telegram_id or not cartella_num:
return jsonify({"error": "መረጃው አልተሟላም!"}), 400

conn = get_db()
cursor = conn.cursor()

user = cursor.execute('SELECT balance FROM users WHERE telegram_id = ?', (telegram_id,)).fetchone()
if not user or user['balance'] < stake:
conn.close()
return jsonify({"error": "በቂ ባላንስ የሎትም! እባክዎን አስቀድመው ሂሳብ ይሙሉ"}), 400

card = {
'B': random.sample(range(1, 16), 5),
'I': random.sample(range(16, 31), 5),
'N': random.sample(range(31, 46), 5),
'G': random.sample(range(46, 61), 5),
'O': random.sample(range(61, 76), 5)
}
card['N'][2] = '★'

cursor.execute('UPDATE users SET balance = balance - ? WHERE telegram_id = ?', (stake, telegram_id))
cursor.execute('INSERT INTO user_cards (telegram_id, cartella_number, stake, card_data) VALUES (?, ?, ?, ?)',
(telegram_id, cartella_num, stake, json.dumps(card)))

conn.commit()
conn.close()

return jsonify({"status": "success", "card": card, "cartella_num": cartella_num})

==========================================
CLAIM BINGO (WINNER REWARD LOGIC)
==========================================
@app.route('/api/game/claim-bingo', methods=['POST'])
def claim_bingo():
data = request.json or {}
telegram_id = data.get('telegram_id')
stake = float(data.get('stake', 10.0))

conn = get_db()
cursor = conn.cursor()

player_count = cursor.execute('SELECT COUNT(DISTINCT telegram_id) as count FROM user_cards WHERE stake = ?', (stake,)).fetchone()['count']
if player_count == 0: player_count = 1

total_pot = player_count * stake
derash_reward = total_pot * (1.0 - COMMISSION_RATE)

# አሸናፊውን ብር ወደ ዋሌት ማስገባት
cursor.execute('UPDATE users SET balance = balance + ? WHERE telegram_id = ?', (derash_reward, telegram_id))
cursor.execute('INSERT INTO transactions (telegram_id, amount, type, method, status) VALUES (?, ?, "bingo_win", "game", "approved")', (telegram_id, derash_reward))

conn.commit()
conn.close()

return jsonify({"status": "success", "message": f"እንኳን ደስ አለዎት! ቢንጎ ሰርተዋል፡ {derash_reward:.2f} ETB ወደ ዋሌትዎ ገብቷል!", "reward": derash_reward})

==========================================
WITHDRAWAL (DAILY LIMIT 2000 & 50 ETB MIN BAL)
==========================================
@app.route('/api/withdraw', methods=['POST'])
def withdraw():
data = request.json or {}
telegram_id = data.get('telegram_id')
phone = str(data.get('phone', '')).strip()
amount = float(data.get('amount', 0))

if not telegram_id or not phone or amount <= 0:
return jsonify({"error": "ትክክለኛ የስልክ ቁጥር እና የመጠነ ገንዘብ ያስገቡ!"}), 400

conn = get_db()
cursor = conn.cursor()

user = cursor.execute('SELECT balance, phone_number FROM users WHERE telegram_id = ?', (telegram_id,)).fetchone()
if not user:
conn.close()
return jsonify({"error": "ተጫዋቹ አልተገኘም!"}), 404

# 1. 50 ETB ቀሪ ባላንስ መኖር አለበት
if (user['balance'] - amount) < MIN_REMAINING_BALANCE:
conn.close()
return jsonify({"error": f"ወጪ ማድረግ አይችሉም! ከወጪ በኋላቢያንስ {MIN_REMAINING_BALANCE} ETB በቀሪነት መቅረት አለበት።"}), 400

# 2. በቀን ከ 2000 ETB በላይ አለመሆኑን ማረጋገጥ
today_spent = cursor.execute('''
SELECT SUM(amount) as total FROM transactions
WHERE telegram_id = ? AND type IN ('withdraw', 'transfer_out')
AND date(date) = date('now')
''', (telegram_id,)).fetchone()['total'] or 0.0

if (today_spent + amount) > DAILY_LIMIT:
conn.close()
return jsonify({"error": f"የቀን የትራንዛክሽን ገደብ አልፈዋል! በቀን ማወጣት/ማስተላለፍ የሚችሉት ቢበዛ {DAILY_LIMIT} ETB ነው። (ዛሬ የተጠቀሙት: {today_spent} ETB)"}), 400

# የስልክ ቁጥሩን በሲስተሙ ይመዘግበዋል
cursor.execute('UPDATE users SET phone_number = ?, balance = balance - ? WHERE telegram_id = ?', (phone, amount, telegram_id))
cursor.execute('INSERT INTO transactions (telegram_id, amount, type, method, status) VALUES (?, ?, "withdraw", "telebirr", "approved")', (telegram_id, amount))

conn.commit()
conn.close()

return jsonify({"status": "success", "message": f"{amount} ETB ወደ {phone} ለማውጣት የቀረበው ጥያቄ ተሳክቷል!"})

==========================================
TRANSFER (DAILY LIMIT 2000 & 50 ETB MIN BAL)
==========================================
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
if not sender:
conn.close()
return jsonify({"error": "ተላኪው አልተገኘም!"}), 404

if (sender['balance'] - amount) < MIN_REMAINING_BALANCE:
conn.close()
return jsonify({"error": f"ትራንስፈር ማድረግ አይችሉም! ቢያንስ {MIN_REMAINING_BALANCE} ETB በቀሪነት መቅረት አለበት።"}), 400

today_spent = cursor.execute('''
SELECT SUM(amount) as total FROM transactions
WHERE telegram_id = ? AND type IN ('withdraw', 'transfer_out')
AND date(date) = date('now')
''', (sender_id,)).fetchone()['total'] or 0.0

if (today_spent + amount) > DAILY_LIMIT:
conn.close()
return jsonify({"error": f"የቀን የትራንዛክሽን ገደብ አልፈዋል! በቀን ቢበዛ {DAILY_LIMIT} ETB ማስተላለፍ/ማውጣት ይቻላል።"}), 400

recipient = cursor.execute('SELECT telegram_id FROM users WHERE telegram_id = ? OR phone_number = ?', (receiver, receiver)).fetchone()
if not recipient:
conn.close()
return jsonify({"error": "ተቀባዩ በሲስተሙ ውስጥ አልተገኘም!"}), 404

cursor.execute('UPDATE users SET balance = balance - ? WHERE telegram_id = ?', (amount, sender_id))
cursor.execute('UPDATE users SET balance = balance + ? WHERE telegram_id = ?', (amount, recipient['telegram_id']))

cursor.execute('INSERT INTO transactions (telegram_id, amount, type, method, status) VALUES (?, ?, "transfer_out", "wallet", "approved")', (sender_id, amount))

conn.commit()
conn.close()

return jsonify({"status": "success", "message": f"{amount} ETB በስኬት ተላክቷል!"})

==========================================
TELEBIRR DEPOSIT AUTOMATION
==========================================
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

amount_match = re.search(r'(?:ETB|ብር)\s*([\d.]+)|([\d.]+)\s*(?:ETB|ብር)', sms_text, re.IGNORECASE)
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

if name == 'main':
app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))

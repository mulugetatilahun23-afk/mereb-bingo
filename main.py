from flask import Flask, request, jsonify, render_template_string
import sqlite3
import os
import random
import json
import re
import urllib.parse
import string
from datetime import datetime

app = Flask(__name__)

# Environment Variables
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
BOT_USERNAME = os.environ.get("BOT_USERNAME", "MerebBingoBot")
DB_NAME = 'mereb_bingo.db'

MERCHANT_PHONE = "0923410403"
MERCHANT_NAME = "MULUGETA TILAHUN"
DAILY_LIMIT = 2000.0  
MIN_REMAINING_BALANCE = 50.0  

# Commission Settings (Total 20% -> 15% Admin / 5% Agent)
TOTAL_COMMISSION_RATE = 0.20  # 20% ጠቅላላ የቤት ኮሚሽን
AGENT_COMMISSION_RATE = 0.05  # 5% ለኤጀንቱ
ADMIN_COMMISSION_RATE = 0.15  # 15% ለዋናው አድሚን

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
            is_agent INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
            room_code TEXT DEFAULT 'GLOBAL',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS group_rooms (
            room_code TEXT PRIMARY KEY,
            host_id INTEGER,
            stake REAL,
            status TEXT DEFAULT 'waiting',
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

    conn.commit()
    conn.close()

init_db()

def generate_room_code():
    return 'ROOM-' + ''.join(random.choices(string.ascii_uppercase + string.digits, k=5))

@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "alive", "project": "Mereb Bingo"}), 200

# ==========================================
# FRONTEND MINI APP
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
                .menu-card { background: #16212e; padding: 14px; border-radius: 8px; text-align: center; font-weight: bold; cursor: pointer; border: 1px solid #233346; }
                .menu-card:active { background: #233346; }
                
                .page-view { display: none; }
                .active-view { display: block; }
                .modal { display: none; position: fixed; bottom: 0; left: 0; right: 0; background: #15202d; padding: 20px; border-top-left-radius: 15px; border-top-right-radius: 15px; box-shadow: 0 -5px 15px rgba(0,0,0,0.5); z-index: 100; max-height: 80vh; overflow-y: auto; }
                input, textarea, button { width: 100%; padding: 12px; margin: 8px 0; border-radius: 6px; border: none; box-sizing: border-box; }
                button { background-color: #2481cc; color: white; font-weight: bold; cursor: pointer; }
                
                .stake-opts { display: flex; gap: 8px; margin: 10px 0; }
                .stake-btn { background: #1e2c3d; border: 1px solid #324760; color: #fff; flex: 1; padding: 10px; border-radius: 8px; font-size: 14px; font-weight: bold; }
                .stake-btn.selected { background: #00c853; border-color: #00c853; }

                .cartella-header { display: flex; justify-content: space-between; background: #16212e; padding: 10px; border-radius: 8px; font-size: 12px; margin-bottom: 10px; text-align: center; }
                .cartella-grid { display: grid; grid-template-columns: repeat(10, 1fr); gap: 4px; max-height: 320px; overflow-y: auto; background: #111a26; padding: 8px; border-radius: 8px; }
                .cartella-num { background: #1c2938; border: 1px solid #2a3d54; color: #fff; text-align: center; padding: 8px 0; border-radius: 50%; font-size: 11px; font-weight: bold; cursor: pointer; }
                .cartella-num.selected { background: #ff5252; border-color: #ff5252; }
                
                .bingo-card { background: #16212e; padding: 12px; border-radius: 12px; max-width: 340px; margin: 0 auto; border: 1px solid #253549; }
                .bingo-grid { display: grid; grid-template-columns: repeat(5, 1fr); gap: 6px; margin-top: 10px; }
                .bingo-cell { background: #223144; color: #fff; text-align: center; height: 48px; display: flex; align-items: center; justify-content: center; font-weight: bold; border-radius: 6px; font-size: 15px; }
                .bingo-cell.header-cell { background: #2d415a; color: #4bc0c0; font-size: 16px; font-weight: 900; }
                .bingo-cell.star-cell { background: #00c853; color: #fff; font-size: 20px; }

                .profile-card { background: #1c2a38; border: 1px solid #2e4359; border-radius: 10px; padding: 12px; margin-bottom: 15px; }
                .profile-row { display: flex; justify-content: space-between; padding: 4px 0; font-size: 13px; color: #ddd; }
                .leaderboard-list { list-style: none; padding: 0; margin: 0; }
                .leaderboard-item { display: flex; justify-content: space-between; background: #16212e; padding: 10px; margin-bottom: 6px; border-radius: 6px; font-size: 13px; }
            </style>
        </head>
        <body>

            <!-- Home Dashboard -->
            <div id="home-view" class="page-view active-view">
                <div class="header">
                    <div>
                        <h3 style="margin:0;">ሜረብ ቢንጎ</h3>
                        <small id="user-display">Loading...</small>
                    </div>
                    <div class="balance-box">
                        ባላንስ: <b id="main-balance">0.00</b> ETB<br>
                        <small style="color:#aaa;" id="user-phone-disp">--</small>
                    </div>
                </div>

                <div class="menu-grid">
                    <div class="menu-card" style="background:#00c853; grid-column: span 2;" onclick="openModal('stake-modal')">▶ START PLAY</div>
                    <div class="menu-card" onclick="openModal('deposit-modal')">📥 Deposit</div>
                    <div class="menu-card" onclick="openModal('withdraw-modal')">📤 Withdraw</div>
                    <div class="menu-card" onclick="openModal('transfer-modal')">💸 Transfer</div>
                    <div class="menu-card" style="background:#ff9800;" onclick="loadAgentDashboard()">💼 Agent Panel</div>
                    <div class="menu-card" onclick="openModal('promo-modal')">🎁 Promo Code</div>
                    <div class="menu-card" onclick="loadLeaderboard()">🏆 Leaderboard</div>
                    <div class="menu-card" onclick="openSection('support')">💬 Support</div>
                </div>
            </div>

            <!-- Registration Phone Modal -->
            <div id="register-modal" class="modal" style="z-index: 200;">
                <h3 style="margin-top:0; color:#00c853;">እንኳን ደህና መጡ!</h3>
                <p style="font-size:13px; color:#ccc;">ለመመዝገብ እና ጨዋታውን ለመጀመር እባክዎን የቴሌግራም ስልክ ቁጥርዎን ያስገቡ።</p>
                <input type="text" id="reg-phone-input" placeholder="ስልክ ቁጥር (ምሳሌ፡ 0912345678)">
                <button onclick="registerPhone()">መዝግብ እና ጀምር (Register)</button>
            </div>

            <!-- Stake & Mode Selection Modal -->
            <div id="stake-modal" class="modal">
                <h4 style="margin-top:0;">የጨዋታ አይነት እና ውርርድ ይምረጡ</h4>
                <div class="stake-opts">
                    <button class="stake-btn selected" id="stake-10" onclick="setStake(10)">10 ETB</button>
                    <button class="stake-btn" id="stake-20" onclick="setStake(20)">20 ETB</button>
                    <button class="stake-btn" id="stake-30" onclick="setStake(30)">30 ETB</button>
                </div>

                <button style="background:#2481cc; margin-bottom:8px;" onclick="proceedToCartellaSelection('GLOBAL')">🌐 መደበኛ ጨዋታ (Global Play)</button>
                <button style="background:#ff9800;" onclick="showGroupOptions()">👥 የቡድን ጨዋታ (Group Play)</button>

                <div id="group-options-box" style="display:none; margin-top:10px; border-top:1px solid #333; padding-top:10px;">
                    <button style="background:#00c853;" onclick="createGroupRoom()">➕ የቡድን ጨዋታ ክፈት (Create Group)</button>
                    <input type="text" id="group-code-input" placeholder="የቡድን ኮድ ያስገቡ (e.g. ROOM-XXXXX)">
                    <button style="background:#9c27b0;" onclick="joinGroupRoom()">🔗 ቡድን ይቀላቀሉ (Join Group)</button>
                </div>

                <button style="background:#e53935; margin-top:10px;" onclick="closeModal('stake-modal')">ተመለስ</button>
            </div>

            <!-- Cartella Selection View (1-300) -->
            <div id="cartella-view" class="page-view">
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px;">
                    <button style="width:auto; margin:0; padding:6px 12px;" onclick="exitCartellaView()">← Back</button>
                    <span><b>Select Cartella</b> (1-300)</span>
                </div>

                <div class="cartella-header">
                    <div>TIMER<br><b id="timer-val" style="color:#ff5252;">30</b></div>
                    <div>DERASH<br><b id="derash-val">0.00</b> ETB</div>
                    <div>STAKE<br><b id="disp-stake">10</b> ETB</div>
                    <div>PLAYERS<br><b id="players-val">1</b></div>
                </div>

                <div class="cartella-grid" id="cartella-container"></div>
                <button style="margin-top:12px;" onclick="confirmCartellaSelection()">ካርቴላ አረጋግጥ (Join Game)</button>
            </div>

            <!-- Active Bingo Game View -->
            <div id="game-view" class="page-view">
                <div style="background: #1e3c72; padding: 12px; border-radius: 10px; text-align: center; margin-bottom: 15px;">
                    <h3 style="margin:0; color:#ffb300;" id="game-room-title">Global Match</h3>
                    <p style="margin:5px 0 0 0;" id="winner-text">Game in Progress...</p>
                </div>

                <div class="bingo-card">
                    <div style="display:flex; justify-content:space-between; font-size:12px; color:#aaa; margin-bottom:5px;">
                        <span id="card-title">Cartella #--</span>
                        <span>Owner: You</span>
                    </div>

                    <div class="bingo-grid" id="bingo-board"></div>
                </div>

                <div style="text-align:center; margin-top:20px;">
                    <button style="width:auto; padding:12px 24px; background:#00c853; font-size:16px;" onclick="claimBingo()">🔥 BINGO! (Claim Win)</button>
                </div>
            </div>

            <!-- Agent Dashboard Modal -->
            <div id="agent-modal" class="modal">
                <h3 style="margin-top:0; color:#ff9800;">💼 የኤጀንት ዳሽቦርድ (Agent Panel)</h3>
                
                <div id="agent-active-section" style="display:none;">
                    <div class="profile-card">
                        <div class="profile-row"><span>የኤጀንት ሁኔታ:</span> <b style="color:#00c853;">የተረጋገጠ ኤጀንት ✔</b></div>
                        <div class="profile-row"><span>የተጋበዙ ተጫዋቾች:</span> <b id="agent-total-users">0</b></div>
                        <div class="profile-row"><span>የተገኘ 5% ኮሚሽን:</span> <b id="agent-comm-earned" style="color:#ffb300;">0.00 ETB</b></div>
                    </div>
                    <p style="font-size:12px; color:#aaa;">የእርሶ ልዩ የኤጀንት ሊንክ (ተጫዋቾች በዚህ ሊንክ ሲገቡ 5% ኮሚሽን ያገኛሉ)፡</p>
                    <button style="background:#00c853;" onclick="shareAgentLink()">🔗 የኤጀንት ሊንክ አጋራ (Share Agent Link)</button>
                </div>

                <div id="agent-register-section" style="display:none; text-align:center;">
                    <p style="font-size:13px; color:#ccc;">እስካሁን ኤጀንት አልሆኑም። ኤጀንት በመሆን በርስዎ ሊንክ በሚገቡ ተጫዋቾች <b>5% ኮሚሽን</b> ማግኘት ይጀምሩ!</p>
                    <button style="background:#ff9800;" onclick="registerAsAgent()">💼 አሁኑኑ ኤጀንት ይሁኑ (Become Agent)</button>
                </div>

                <button style="background:#e53935; margin-top:10px;" onclick="closeModal('agent-modal')">ዝጋ</button>
            </div>

            <!-- Leaderboard & Profile View -->
            <div id="leaderboard-view" class="page-view">
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px;">
                    <button style="width:auto; margin:0; padding:6px 12px;" onclick="showView('home-view')">← Back</button>
                    <h3 style="margin:0;">Leaderboard & Profile</h3>
                </div>

                <div class="profile-card">
                    <h4 style="margin:0 0 8px 0; color:#4bc0c0;">👤 የእርሶ ፕሮፋይል (Your Profile)</h4>
                    <div class="profile-row"><span>ስም:</span> <b id="prof-name">--</b></div>
                    <div class="profile-row"><span>Telegram ID:</span> <b id="prof-id">--</b></div>
                    <div class="profile-row"><span>ስልክ:</span> <b id="prof-phone">--</b></div>
                    <div class="profile-row"><span>ዋና ባላንስ:</span> <b id="prof-bal">0.00 ETB</b></div>
                    <div class="profile-row"><span>የኮሚሽን ባላንስ (5%):</span> <b id="prof-comm">0.00 ETB</b></div>
                </div>

                <h4>🏆 ከፍተኛ አሸናፊዎች (Top Players)</h4>
                <div class="leaderboard-list" id="leaderboard-container"></div>
            </div>

            <!-- Other Modals -->
            <div id="deposit-modal" class="modal">
                <h4>በቴሌብር ሂሳብ መሙያ</h4>
                <p style="font-size: 11px; color: #aaa;">ገንዘቡን ወደ <b>0923410403 (Mulugeta Tilahun)</b> ከላኩ በኋላ ከቴሌብር የደረሰዎትን SMS እዚህ ይለጥፉ።</p>
                <textarea id="deposit-sms" rows="4" placeholder="ከቴሌብር የደረሰዎትን ሙሉ SMS ይለጥፉ..."></textarea>
                <button onclick="submitTelebirrSMS()">ማረጋገጫ ላክ (Verify)</button>
                <button style="background:#e53935;" onclick="closeModal('deposit-modal')">ዝጋ</button>
            </div>

            <div id="withdraw-modal" class="modal">
                <h4>ገንዘብ ማውጫ (Withdraw)</h4>
                <input type="text" id="withdraw-phone" placeholder="የቴሌብር ስልክ ቁጥር (09...)">
                <input type="number" id="withdraw-amount" placeholder="የሚወጣው ብር መጠን">
                <button onclick="submitWithdraw()">ወጪ አድርግ (Withdraw)</button>
                <button style="background:#e53935;" onclick="closeModal('withdraw-modal')">ዝጋ</button>
            </div>

            <div id="transfer-modal" class="modal">
                <h4>Transfer Money</h4>
                <input type="text" id="transfer-receiver" placeholder="የተቀባይ Telegram ID ወይም ስልክ">
                <input type="number" id="transfer-amount" placeholder="የገንዘብ መጠን (ETB)">
                <button onclick="submitTransfer()">አስተላልፍ (Transfer)</button>
                <button style="background:#e53935;" onclick="closeModal('transfer-modal')">ዝጋ</button>
            </div>

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
                const startParam = tg.initDataUnsafe?.start_param || ""; 

                let currentStake = 10;
                let currentRoomCode = 'GLOBAL';
                let selectedCartella = null;
                let timerInterval = null;

                // Sync User with Referral / Agent Check
                fetch('/api/sync-user', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ 
                        telegram_id: user.id, 
                        first_name: user.first_name,
                        start_param: startParam 
                    })
                }).then(res => res.json()).then(data => {
                    if(data.status === 'success'){
                        document.getElementById('user-display').innerText = data.user.first_name;
                        document.getElementById('main-balance').innerText = data.user.balance.toFixed(2);
                        document.getElementById('user-phone-disp').innerText = data.user.phone_number || "ያልተመዘገበ";

                        if(!data.user.phone_number) {
                            openModal('register-modal');
                        }
                    }
                });

                function registerPhone() {
                    const phone = document.getElementById('reg-phone-input').value.trim();
                    if(!phone) return alert("እባክዎን ስልክ ቁጥር ያስገቡ!");

                    fetch('/api/register-phone', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ telegram_id: user.id, phone: phone })
                    }).then(r => r.json()).then(res => {
                        if(res.status === 'success') {
                            alert("በስኬት ተመዝግበዋል!");
                            closeModal('register-modal');
                            location.reload();
                        } else {
                            alert(res.error);
                        }
                    });
                }

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

                function showGroupOptions() {
                    const box = document.getElementById('group-options-box');
                    box.style.display = box.style.display === 'none' ? 'block' : 'none';
                }

                function createGroupRoom() {
                    fetch('/api/group/create', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ telegram_id: user.id, stake: currentStake })
                    }).then(r => r.json()).then(res => {
                        if(res.status === 'success') {
                            alert("የቡድን ጨዋታ ተከፍቷል!\nየቡድን ኮድ: " + res.room_code + "\n\nሊንኩን ለጓደኞችዎ ያጋሩ!");
                            tg.openTelegramLink(res.share_link);
                            proceedToCartellaSelection(res.room_code);
                        } else {
                            alert(res.error);
                        }
                    });
                }

                function joinGroupRoom() {
                    const code = document.getElementById('group-code-input').value.trim().toUpperCase();
                    if(!code) return alert("እባክዎን የቡድን ኮድ ያስገቡ!");

                    fetch('/api/group/join', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ room_code: code })
                    }).then(r => r.json()).then(res => {
                        if(res.status === 'success') {
                            setStake(res.stake);
                            proceedToCartellaSelection(res.room_code);
                        } else {
                            alert(res.error);
                        }
                    });
                }

                function proceedToCartellaSelection(roomCode = 'GLOBAL') {
                    currentRoomCode = roomCode;
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
                            alert("የምርጫ ጊዜ አልቋል!");
                            showView('home-view');
                        }
                    }, 1000);
                }

                function exitCartellaView() {
                    if(timerInterval) clearInterval(timerInterval);
                    showView('home-view');
                }

                function fetchGameStats() {
                    fetch('/api/game/stats?stake=' + currentStake + '&room=' + currentRoomCode)
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
                        body: JSON.stringify({ telegram_id: user.id, cartella_num: selectedCartella, stake: currentStake, room_code: currentRoomCode })
                    }).then(r => r.json()).then(res => {
                        if (res.status === 'success') {
                            if(timerInterval) clearInterval(timerInterval);
                            renderBingoBoard(res.card, selectedCartella);
                            document.getElementById('game-room-title').innerText = currentRoomCode === 'GLOBAL' ? 'Global Match' : 'Group: ' + currentRoomCode;
                            showView('game-view');
                        } else {
                            alert(res.error);
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
                            cell.className = (val === '★' || val === 'FREE') ? 'bingo-cell star-cell' : 'bingo-cell';
                            cell.innerText = (val === '★' || val === 'FREE') ? '★' : val;
                            board.appendChild(cell);
                        });
                    }
                }

                function claimBingo() {
                    fetch('/api/game/claim-bingo', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ telegram_id: user.id, stake: currentStake, room_code: currentRoomCode })
                    }).then(r => r.json()).then(res => {
                        alert(res.message || res.error);
                        if(res.status === 'success') {
                            document.getElementById('winner-text').innerText = user.first_name + " won " + res.reward + " ETB!";
                        }
                    });
                }

                // ================= Agent Functions =================
                function loadAgentDashboard() {
                    fetch('/api/agent/stats?telegram_id=' + user.id)
                        .then(r => r.json())
                        .then(res => {
                            if(res.status === 'success') {
                                openModal('agent-modal');
                                if(res.is_agent) {
                                    document.getElementById('agent-active-section').style.display = 'block';
                                    document.getElementById('agent-register-section').style.display = 'none';
                                    document.getElementById('agent-total-users').innerText = res.total_referred_users;
                                    document.getElementById('agent-comm-earned').innerText = res.commission_balance.toFixed(2) + " ETB";
                                } else {
                                    document.getElementById('agent-active-section').style.display = 'none';
                                    document.getElementById('agent-register-section').style.display = 'block';
                                }
                            }
                        });
                }

                function registerAsAgent() {
                    fetch('/api/agent/register', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ telegram_id: user.id })
                    }).then(r => r.json()).then(res => {
                        if(res.status === 'success') {
                            alert("እንኳን ደስ አለዎት! አሁን ኤጀንት ሆነዋል።");
                            loadAgentDashboard();
                        }
                    });
                }

                function shareAgentLink() {
                    fetch('/api/agent/share-link', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ telegram_id: user.id })
                    }).then(r => r.json()).then(res => {
                        if(res.status === 'success') {
                            tg.openTelegramLink(res.share_link);
                        }
                    });
                }

                function loadLeaderboard() {
                    fetch('/api/leaderboard?telegram_id=' + user.id)
                        .then(r => r.json())
                        .then(res => {
                            if(res.status === 'success') {
                                document.getElementById('prof-name').innerText = res.profile.first_name;
                                document.getElementById('prof-id').innerText = res.profile.telegram_id;
                                document.getElementById('prof-phone').innerText = res.profile.phone_number || "ያልተመዘገበ";
                                document.getElementById('prof-bal').innerText = res.profile.balance.toFixed(2) + " ETB";
                                document.getElementById('prof-comm').innerText = res.profile.commission_balance.toFixed(2) + " ETB";

                                const container = document.getElementById('leaderboard-container');
                                container.innerHTML = '';
                                res.leaderboard.forEach((item, idx) => {
                                    const div = document.createElement('div');
                                    div.className = 'leaderboard-item';
                                    div.innerHTML = `<span>#${idx+1} ${item.first_name}</span><b>${item.balance.toFixed(2)} ETB</b>`;
                                    container.appendChild(div);
                                });
                                showView('leaderboard-view');
                            }
                        });
                }

                function openSection(type) {
                    if (type === 'support') {
                        tg.openTelegramLink('https://t.me/merebbingosupport');
                    }
                }

                function submitTelebirrSMS() {
                    const smsText = document.getElementById('deposit-sms').value;
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

# ==========================================
# USER SYNC & AGENT REFERRAL HANDLING
# ==========================================
@app.route('/api/sync-user', methods=['POST'])
def sync_user():
    data = request.json or {}
    telegram_id = data.get('telegram_id')
    first_name = data.get('first_name', '')
    start_param = str(data.get('start_param', '')).strip()

    if not telegram_id:
        return jsonify({"error": "telegram_id ያስፈልጋል!"}), 400

    agent_id = None
    if start_param.startswith('agent_'):
        try:
            agent_id = int(start_param.replace('agent_', ''))
        except:
            agent_id = None

    conn = get_db()
    cursor = conn.cursor()
    user = cursor.execute('SELECT * FROM users WHERE telegram_id = ?', (telegram_id,)).fetchone()

    if not user:
        cursor.execute('INSERT INTO users (telegram_id, first_name, agent_id) VALUES (?, ?, ?)', 
                       (telegram_id, first_name, agent_id if agent_id != telegram_id else None))
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
            "phone_number": updated_user['phone_number'],
            "balance": updated_user['balance'],
            "commission_balance": updated_user['commission_balance'],
            "is_agent": updated_user['is_agent']
        }
    })

@app.route('/api/register-phone', methods=['POST'])
def register_phone():
    data = request.json or {}
    telegram_id = data.get('telegram_id')
    phone = str(data.get('phone', '')).strip()

    if not telegram_id or not phone:
        return jsonify({"error": "ትክክለኛ ስልክ ቁጥር ያስገቡ!"}), 400

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET phone_number = ? WHERE telegram_id = ?', (phone, telegram_id))
    conn.commit()
    conn.close()

    return jsonify({"status": "success", "message": "ስልክ ቁጥር በስኬት ተመዝግቧል!"})

# ==========================================
# AGENT MANAGEMENT APIS
# ==========================================
@app.route('/api/agent/register', methods=['POST'])
def register_agent():
    telegram_id = (request.json or {}).get('telegram_id')
    if not telegram_id:
        return jsonify({"error": "telegram_id ያስፈልጋል"}), 400

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET is_agent = 1 WHERE telegram_id = ?', (telegram_id,))
    conn.commit()
    conn.close()

    return jsonify({"status": "success", "message": "በስኬት ኤጀንት ሆነዋል!"})

@app.route('/api/agent/stats', methods=['GET'])
def agent_stats():
    telegram_id = request.args.get('telegram_id')
    conn = get_db()
    cursor = conn.cursor()

    user = cursor.execute('SELECT is_agent, commission_balance FROM users WHERE telegram_id = ?', (telegram_id,)).fetchone()
    if not user:
        conn.close()
        return jsonify({"error": "ተጠቃሚው አልተገኘም"}), 404

    referred_count = cursor.execute('SELECT COUNT(*) as count FROM users WHERE agent_id = ?', (telegram_id,)).fetchone()['count']
    conn.close()

    return jsonify({
        "status": "success",
        "is_agent": bool(user['is_agent']),
        "total_referred_users": referred_count,
        "commission_balance": user['commission_balance']
    })

@app.route('/api/agent/share-link', methods=['POST'])
def agent_share_link():
    telegram_id = (request.json or {}).get('telegram_id')
    agent_link = f"https://t.me/{BOT_USERNAME}/app?startapp=agent_{telegram_id}"
    text = urllib.parse.quote("🎯 በሜረብ ቢንጎ ይጫወቱ እና ያሸንፉ! በልዩ ኤጀንት ሊንክ ይመዝገቡ፡")
    
    return jsonify({
        "status": "success", 
        "share_link": f"https://t.me/share/url?url={agent_link}&text={text}"
    })

# ==========================================
# BINGO CLAIM WITH 15% / 5% COMMISSION SPLIT
# ==========================================
@app.route('/api/game/claim-bingo', methods=['POST'])
def claim_bingo():
    data = request.json or {}
    winner_id = data.get('telegram_id')
    stake = float(data.get('stake', 10.0))
    room_code = data.get('room_code', 'GLOBAL')

    conn = get_db()
    cursor = conn.cursor()

    # Get players count & total pot
    player_count = cursor.execute('SELECT COUNT(DISTINCT telegram_id) as count FROM user_cards WHERE stake = ? AND room_code = ?', 
                                  (stake, room_code)).fetchone()['count']
    if player_count == 0: player_count = 1

    total_pot = player_count * stake
    winner_reward = total_pot * (1.0 - TOTAL_COMMISSION_RATE) # 80% ለአሸናፊው

    # 1. አሸናፊውን ሂሳብ ማስገባት
    cursor.execute('UPDATE users SET balance = balance + ? WHERE telegram_id = ?', (winner_reward, winner_id))
    cursor.execute('INSERT INTO transactions (telegram_id, amount, type, method) VALUES (?, ?, "bingo_win", "game")', (winner_id, winner_reward))

    # 2. የኮሚሽን ክፍፍል (15% Admin / 5% Agent)
    # አሸናፊውን ያመጣው ኤጀንት ካለ ይፈተሻል
    winner_user = cursor.execute('SELECT agent_id FROM users WHERE telegram_id = ?', (winner_id,)).fetchone()
    
    if winner_user and winner_user['agent_id']:
        agent_id = winner_user['agent_id']
        agent_cut = total_pot * AGENT_COMMISSION_RATE  # 5% ለኤጀንቱ
        admin_cut = total_pot * ADMIN_COMMISSION_RATE  # 15% ለአድሚኑ

        # የኤጀንቱን 5% ኮሚሽን ባላንስ ላይ መጨመር
        cursor.execute('UPDATE users SET commission_balance = commission_balance + ?, balance = balance + ? WHERE telegram_id = ?', 
                       (agent_cut, agent_cut, agent_id))
        cursor.execute('INSERT INTO transactions (telegram_id, amount, type, method) VALUES (?, ?, "agent_commission_5pct", "referral")', (agent_id, agent_cut))
    else:
        # ኤጀንት ከሌለ ሙሉው 20% ለአድሚን ገቢ ይሆናል
        admin_cut = total_pot * TOTAL_COMMISSION_RATE

    conn.commit()
    conn.close()

    return jsonify({
        "status": "success", 
        "message": f"እንኳን ደስ አለዎት! {winner_reward:.2f} ETB አሸንፈዋል!", 
        "reward": winner_reward
    })

# ==========================================
# GROUP PLAY ROOM APIS
# ==========================================
@app.route('/api/group/create', methods=['POST'])
def create_group():
    data = request.json or {}
    telegram_id = data.get('telegram_id')
    stake = float(data.get('stake', 10.0))

    room_code = generate_room_code()
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute('INSERT INTO group_rooms (room_code, host_id, stake) VALUES (?, ?, ?)', 
                   (room_code, telegram_id, stake))
    conn.commit()
    conn.close()

    share_text = f"🎮 የቢንጎ ቡድን ጨዋታ ተከፍቷል! በ {stake} ETB ይጫወቱ።\nየቡድን ኮድ: {room_code}"
    encoded = urllib.parse.quote(share_text)
    share_link = f"https://t.me/share/url?url=https://t.me/{BOT_USERNAME}/app?startapp={room_code}&text={encoded}"

    return jsonify({"status": "success", "room_code": room_code, "stake": stake, "share_link": share_link})

@app.route('/api/group/join', methods=['POST'])
def join_group():
    data = request.json or {}
    room_code = str(data.get('room_code', '')).strip().upper()

    conn = get_db()
    cursor = conn.cursor()
    room = cursor.execute('SELECT * FROM group_rooms WHERE room_code = ?', (room_code,)).fetchone()
    conn.close()

    if not room:
        return jsonify({"error": "የቡድን ኮዱ አልተገኘም!"}), 404

    return jsonify({"status": "success", "room_code": room['room_code'], "stake": room['stake']})

# ==========================================
# GAME STATS & CARTELLA GENERATION
# ==========================================
@app.route('/api/game/stats', methods=['GET'])
def game_stats():
    stake = float(request.args.get('stake', 10.0))
    room_code = request.args.get('room', 'GLOBAL')

    conn = get_db()
    cursor = conn.cursor()
    
    player_count = cursor.execute('SELECT COUNT(DISTINCT telegram_id) as count FROM user_cards WHERE stake = ? AND room_code = ?', 
                                  (stake, room_code)).fetchone()['count']
    if player_count == 0: player_count = 1

    total_pot = player_count * stake
    derash = total_pot * (1.0 - TOTAL_COMMISSION_RATE)
    conn.close()

    return jsonify({"players": player_count, "derash": derash, "stake": stake})

@app.route('/api/game/generate-card', methods=['POST'])
def generate_card():
    data = request.json or {}
    telegram_id = data.get('telegram_id')
    cartella_num = data.get('cartella_num')
    stake = float(data.get('stake', 10.0))
    room_code = data.get('room_code', 'GLOBAL')

    conn = get_db()
    cursor = conn.cursor()

    user = cursor.execute('SELECT balance FROM users WHERE telegram_id = ?', (telegram_id,)).fetchone()
    if not user or user['balance'] < stake:
        conn.close()
        return jsonify({"error": "በቂ ባላንስ የሎትም! አስቀድመው ሂሳብ ይሙሉ"}), 400

    card = {
        'B': random.sample(range(1, 16), 5),
        'I': random.sample(range(16, 31), 5),
        'N': random.sample(range(31, 46), 5),
        'G': random.sample(range(46, 61), 5),
        'O': random.sample(range(61, 76), 5)
    }
    card['N'][2] = '★'

    cursor.execute('UPDATE users SET balance = balance - ? WHERE telegram_id = ?', (stake, telegram_id))
    cursor.execute('INSERT INTO user_cards (telegram_id, cartella_number, stake, card_data, room_code) VALUES (?, ?, ?, ?, ?)', 
                   (telegram_id, cartella_num, stake, json.dumps(card), room_code))

    conn.commit()
    conn.close()

    return jsonify({"status": "success", "card": card, "cartella_num": cartella_num})

# ==========================================
# LEADERBOARD & PROFILE API
# ==========================================
@app.route('/api/leaderboard', methods=['GET'])
def get_leaderboard():
    telegram_id = request.args.get('telegram_id')
    conn = get_db()
    cursor = conn.cursor()

    profile = cursor.execute('SELECT * FROM users WHERE telegram_id = ?', (telegram_id,)).fetchone()
    top_users = cursor.execute('SELECT first_name, balance FROM users ORDER BY balance DESC LIMIT 10').fetchall()

    leaderboard_data = [{"first_name": u['first_name'], "balance": u['balance']} for u in top_users]
    conn.close()

    return jsonify({
        "status": "success",
        "profile": {
            "first_name": profile['first_name'] if profile else "--",
            "telegram_id": profile['telegram_id'] if profile else "--",
            "phone_number": profile['phone_number'] if profile else "ያልተመዘገበ",
            "balance": profile['balance'] if profile else 0.0,
            "commission_balance": profile['commission_balance'] if profile else 0.0
        },
        "leaderboard": leaderboard_data
    })

# ==========================================
# WITHDRAW, TRANSFER, DEPOSIT & PROMO
# ==========================================
@app.route('/api/withdraw', methods=['POST'])
def withdraw():
    data = request.json or {}
    telegram_id = data.get('telegram_id')
    phone = str(data.get('phone', '')).strip()
    amount = float(data.get('amount', 0))

    if not telegram_id or not phone or amount <= 0:
        return jsonify({"error": "ትክክለኛ መረጃ ያስገቡ!"}), 400

    conn = get_db()
    cursor = conn.cursor()
    user = cursor.execute('SELECT balance FROM users WHERE telegram_id = ?', (telegram_id,)).fetchone()

    if not user or (user['balance'] - amount) < MIN_REMAINING_BALANCE:
        conn.close()
        return jsonify({"error": f"ቢያንስ {MIN_REMAINING_BALANCE} ETB በቀሪነት መቅረት አለበት!"}), 400

    today_spent = cursor.execute('''
        SELECT SUM(amount) as total FROM transactions 
        WHERE telegram_id = ? AND type IN ('withdraw', 'transfer_out') AND date(date) = date('now')
    ''', (telegram_id,)).fetchone()['total'] or 0.0

    if (today_spent + amount) > DAILY_LIMIT:
        conn.close()
        return jsonify({"error": f"የቀን የትራንዛክሽን ገደብ ({DAILY_LIMIT} ETB) አልፈዋል!"}), 400

    cursor.execute('UPDATE users SET phone_number = ?, balance = balance - ? WHERE telegram_id = ?', (phone, amount, telegram_id))
    cursor.execute('INSERT INTO transactions (telegram_id, amount, type, method) VALUES (?, ?, "withdraw", "telebirr")', (telegram_id, amount))

    conn.commit()
    conn.close()
    return jsonify({"status": "success", "message": f"{amount} ETB ወጪ የማድረግ ጥያቄዎ ተሳክቷል!"})

@app.route('/api/transfer', methods=['POST'])
def transfer_money():
    data = request.json or {}
    sender_id = data.get('sender_id')
    receiver = str(data.get('receiver', '')).strip()
    amount = float(data.get('amount', 0))

    conn = get_db()
    cursor = conn.cursor()
    sender = cursor.execute('SELECT balance FROM users WHERE telegram_id = ?', (sender_id,)).fetchone()

    if not sender or (sender['balance'] - amount) < MIN_REMAINING_BALANCE:
        conn.close()
        return jsonify({"error": f"ቢያንስ {MIN_REMAINING_BALANCE} ETB በቀሪነት መቅረት አለበት!"}), 400

    recipient = cursor.execute('SELECT telegram_id FROM users WHERE telegram_id = ? OR phone_number = ?', (receiver, receiver)).fetchone()
    if not recipient:
        conn.close()
        return jsonify({"error": "ተቀባዩ አልተገኘም!"}), 404

    cursor.execute('UPDATE users SET balance = balance - ? WHERE telegram_id = ?', (amount, sender_id))
    cursor.execute('UPDATE users SET balance = balance + ? WHERE telegram_id = ?', (amount, recipient['telegram_id']))
    cursor.execute('INSERT INTO transactions (telegram_id, amount, type, method) VALUES (?, ?, "transfer_out", "wallet")', (sender_id, amount))

    conn.commit()
    conn.close()
    return jsonify({"status": "success", "message": f"{amount} ETB ተላልፏል!"})

@app.route('/api/deposit-telebirr-sms', methods=['POST'])
def deposit_telebirr_sms():
    data = request.json or {}
    telegram_id = data.get('telegram_id')
    sms_text = str(data.get('sms_text', '')).strip()

    if MERCHANT_PHONE not in sms_text and MERCHANT_NAME not in sms_text.upper():
        return jsonify({"error": f"ክፍያው ወደ {MERCHANT_PHONE} መላኩን ያረጋግጡ!"}), 400

    tx_match = re.search(r'\b([A-Z0-9]{10,})\b', sms_text.upper())
    amount_match = re.search(r'(?:ETB|ብር)\s*([\d\.]+)|([\d\.]+)\s*(?:ETB|ብር)', sms_text, re.IGNORECASE)

    if not tx_match or not amount_match:
        return jsonify({"error": "በትራንስክሪፕቱ ላይ የትራንዛክሽን ቁጥር/መጠን ማግኘት አልተቻለም!"}), 400

    tx_id = tx_match.group(1)
    amount = float(amount_match.group(1) or amount_match.group(2))

    conn = get_db()
    cursor = conn.cursor()

    if cursor.execute('SELECT id FROM transactions WHERE tx_id = ?', (tx_id,)).fetchone():
        conn.close()
        return jsonify({"error": "ይህ የትራንዛክሽን ቁጥር ቀደም ሲል ጥቅም ላይ ውሏል!"}), 400

    cursor.execute('INSERT INTO transactions (telegram_id, tx_id, amount, type, method, raw_sms) VALUES (?, ?, ?, "deposit", "telebirr_sms", ?)', 
                   (telegram_id, tx_id, amount, sms_text))
    cursor.execute('UPDATE users SET balance = balance + ? WHERE telegram_id = ?', (amount, telegram_id))

    conn.commit()
    conn.close()
    return jsonify({"status": "success", "message": f"{amount} ETB ወደ አካውንትዎ ተጨምሯል!"})

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
    return jsonify({"status": "success", "message": f"{promo['reward']} ETB ቦነስ አግኝተዋል።"})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))

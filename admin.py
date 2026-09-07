from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

app = Flask(__name__)
# ዳታቤዝ ማገናኛ (ለሙከራ SQLite ጥቅም ላይ ውሏል)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///game_admin.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# ==========================================
# 1. የዳታቤዝ አወቃቀር (Database Models)
# ==========================================

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    balance = db.Column(db.Float, default=0.0)
    status = db.Column(db.String(20), default='Active') # Active ወይም Suspended

class ActivityLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    action = db.Column(db.String(200)) # ለምሳሌ፡ "ጨዋታ ጀመረ", "ገንዘብ አስገባ"
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

class Transaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    amount = db.Column(db.Float)
    transaction_type = db.Column(db.String(50)) # Deposit ወይም Withdrawal
    handled_by_admin = db.Column(db.Boolean, default=False) # በAdmin የተስተካከለ መሆኑን ለመለየት
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

class Promotion(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100))
    description = db.Column(db.Text)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# ==========================================
# 2. የአስተዳዳሪ መቆጣጠሪያ መንገዶች (Admin API Routes)
# ==========================================

# 1. የተጠቃሚዎችን እንቅስቃሴ ማየት
@app.route('/admin/logs/<int:user_id>', methods=['GET'])
def get_user_logs(user_id):
    logs = ActivityLog.query.filter_by(user_id=user_id).order_by(ActivityLog.timestamp.desc()).all()
    log_data = [{"action": log.action, "time": log.timestamp} for log in logs]
    return jsonify({"user_id": user_id, "logs": log_data})

# 2. ሲስተም እምቢ ሲል ገቢና ወጪ ማስተካከል (Manual Transaction)
@app.route('/admin/transaction', methods=['POST'])
def manual_transaction():
    data = request.json
    user = User.query.get(data['user_id'])
    
    if not user:
        return jsonify({"error": "ተጠቃሚው አልተገኘም"}), 404

    amount = data['amount']
    trans_type = data['type'] # 'deposit' ወይም 'withdraw'

    if trans_type == 'deposit':
        user.balance += amount
    elif trans_type == 'withdraw':
        if user.balance >= amount:
            user.balance -= amount
        else:
            return jsonify({"error": "በቂ ቀሪ ሂሳብ የለም"}), 400

    # ትራንዛክሽኑን መመዝገብ
    new_transaction = Transaction(
        user_id=user.id, 
        amount=amount, 
        transaction_type=trans_type, 
        handled_by_admin=True
    )
    
    # ሎግ መመዝገብ
    new_log = ActivityLog(user_id=user.id, action=f"Admin manual {trans_type} of {amount}")
    
    db.session.add(new_transaction)
    db.session.add(new_log)
    db.session.commit()

    return jsonify({"message": "በተሳካ ሁኔታ ተስተካክሏል", "new_balance": user.balance})

# 3. አዲስ ፕሮሞሽን ማውጣት
@app.route('/admin/promotion', methods=['POST'])
def create_promotion():
    data = request.json
    new_promo = Promotion(title=data['title'], description=data['description'])
    db.session.add(new_promo)
    db.session.commit()
    return jsonify({"message": "ፕሮሞሽኑ በተሳካ ሁኔታ ተፈጥሯል!"})

# 4. ተጠቃሚን ማገድ (ተጨማሪ የተካተተ)
@app.route('/admin/user/<int:user_id>/suspend', methods=['PUT'])
def suspend_user(user_id):
    user = User.query.get(user_id)
    if user:
        user.status = 'Suspended'
        db.session.commit()
        return jsonify({"message": f"{user.username} ታግዷል"})
    return jsonify({"error": "ተጠቃሚው አልተገኘም"}), 404

if __name__ == '__main__':
    with app.app_context():
        db.create_all() # ዳታቤዙን ለመፍጠር
    app.run(debug=True)

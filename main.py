from flask import Flask, render_template, request, jsonify
import os

app = Flask(__name__)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/play', methods=['POST'])
def play_game():
    data = request.json
    return jsonify({"status": "success", "message": "ካርዱ በተሳካ ሁኔታ ተልኳል!"})

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)

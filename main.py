from flask import Flask, render_template, request, jsonify
import os

app = Flask(__name__)

@app.route('/')
def index():
    return """
    <html>
        <head><title>Mereb Bingo</title></head>
        <body style="background-color: #121212; color: white; text-align: center; padding-top: 50px; font-family: sans-serif;">
            <h1>Mereb Bingo Mini App is Live!</h1>
            <p>ሰርቨሩ በትክክል እየሰራ ነው። አሁን ጨዋታውን ማቀናበር እንችላለን።</p>
        </body>
    </html>
    """

@app.route('/api/play', methods=['POST'])
def play_game():
    data = request.json
    return jsonify({"status": "success", "message": "ካርዱ በተሳካ ሁኔታ ተልኳል!"})

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)

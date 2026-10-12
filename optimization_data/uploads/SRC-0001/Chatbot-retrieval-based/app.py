
from flask import Flask, render_template, request, jsonify
from chat import chatbot_response
 
app = Flask(__name__)
 
@app.route("/")
def home():
    return render_template("index.html")
 
@app.route("/chat", methods=["POST"])
def chat_api():
    data    = request.get_json(silent=True) or {}
    message = data.get("message", "").strip()
 
    if not message:
        return jsonify({"reply": "Bạn chưa nhập tin nhắn."}), 400
 
    reply = chatbot_response(message)
    return jsonify({"reply": reply})
 
if __name__ == "__main__":
    app.run(debug=True)
 
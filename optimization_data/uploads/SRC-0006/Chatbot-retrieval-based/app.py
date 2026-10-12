from flask import Flask, render_template, request, jsonify, Response, stream_with_context
from chat import chatbot_response, chatbot_response_stream
import json

app = Flask(__name__)

@app.route("/")
def home():
    return render_template("index.html")

# ---------- endpoint cũ (giữ lại để tương thích) ----------
@app.route("/chat", methods=["POST"])
def chat_api():
    data    = request.get_json(silent=True) or {}
    message = data.get("message", "").strip()

    if not message:
        return jsonify({"reply": "Bạn chưa nhập tin nhắn."})

    reply = chatbot_response(message)
    return jsonify({"reply": reply})

# ---------- endpoint streaming (Server-Sent Events) ----------
@app.route("/chat/stream", methods=["POST"])
def chat_stream():
    data    = request.get_json(silent=True) or {}
    message = data.get("message", "").strip()

    if not message:
        def empty():
            yield "data: " + json.dumps({"token": "Bạn chưa nhập tin nhắn."}) + "\n\n"
            yield "data: [DONE]\n\n"
        return Response(stream_with_context(empty()), mimetype="text/event-stream")

    def generate():
        try:
            for token in chatbot_response_stream(message):
                yield "data: " + json.dumps({"token": token}) + "\n\n"
        except Exception as e:
            yield "data: " + json.dumps({"token": f"\n[Lỗi: {str(e)}]"}) + "\n\n"
        finally:
            yield "data: [DONE]\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        }
    )

if __name__ == "__main__":
    app.run(debug=True)
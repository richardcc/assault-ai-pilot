from flask import Flask, send_from_directory, jsonify
import os

app = Flask(__name__)

@app.route("/")
def index():
    return send_from_directory("assault-web", "index.html")

@app.route("/<path:path>")
def web_files(path):
    return send_from_directory("assault-web", path)

# Assets UI (counters, json, maps)
@app.route("/assets/<path:path>")
def assets(path):
    return send_from_directory("assault-web/assets", path)

# Game assets (maps legacy)
@app.route("/game/<path:path>")
def game_assets(path):
    return send_from_directory("assault-web/assets", path)

@app.route("/replays/<path:filename>")
def serve_replay(filename):
    return send_from_directory("replays", filename)

@app.route("/api/replays")
def list_replays():
    files = [f for f in os.listdir("replays") if f.endswith(".json")]
    return jsonify(sorted(files))

if __name__ == "__main__":
    app.run(
        host="127.0.0.1",
        port=8000,
        debug=True
    )

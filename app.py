import base64
import json
import mimetypes
import os
import socket
import uuid

import anthropic
from flask import Flask, render_template, request, jsonify

# RenderなどのホストでIPv6経路が不安定な場合に接続エラーになることがあるため、
# DNS解決をIPv4のみに強制する
_orig_getaddrinfo = socket.getaddrinfo


def _ipv4_only_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    return _orig_getaddrinfo(host, port, socket.AF_INET, type, proto, flags)


socket.getaddrinfo = _ipv4_only_getaddrinfo

app = Flask(__name__)
UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

client = anthropic.Anthropic()  # ANTHROPIC_API_KEY 環境変数を使用

ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string", "description": "フリマアプリ向けの商品タイトル(30文字程度)"},
        "description": {"type": "string", "description": "商品説明文。状態・特徴・サイズ感などを含む"},
        "tags": {
            "type": "array",
            "items": {"type": "string"},
            "description": "検索されやすいタグ・キーワードのリスト(5〜10個)",
        },
        "category_guess": {"type": "string", "description": "推定される商品カテゴリ"},
        "condition_guess": {"type": "string", "description": "写真から判断した商品の状態(新品/未使用に近い/傷や汚れありなど)"},
    },
    "required": ["title", "description", "tags", "category_guess", "condition_guess"],
    "additionalProperties": False,
}

SYSTEM_PROMPT = """あなたはフリマアプリ(メルカリ等)の出品を手伝うアシスタントです。
アップロードされた商品写真を見て、出品に使える情報を日本語で生成してください。

- title: 検索されやすく、商品の特徴が伝わる短いタイトル
- description: 状態・素材・サイズ感・使用感などを具体的に。誇張せず、写真から読み取れる事実を中心に書く
- tags: 商品名、ブランド名(判別できれば)、色、カテゴリなど、検索キーワードになりそうな単語
- category_guess: 商品カテゴリの推定
- condition_guess: 写真から判断できる商品状態の推定

価格については言及しないでください(価格は出力に含めない)。
写真から確実に判断できない情報(ブランド名やサイズなど)は、断定せず「不明」「要確認」等にしてください。
"""


def image_to_content_block(file_storage):
    ext = os.path.splitext(file_storage.filename or "")[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError(f"対応していないファイル形式です: {ext}")

    data = file_storage.read()
    media_type = mimetypes.guess_type(file_storage.filename)[0] or "image/jpeg"
    b64 = base64.standard_b64encode(data).decode("utf-8")

    return {
        "type": "image",
        "source": {"type": "base64", "media_type": media_type, "data": b64},
    }, data, ext


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/analyze", methods=["POST"])
def analyze():
    if "photo" not in request.files:
        return jsonify({"error": "写真が選択されていません"}), 400

    photo = request.files["photo"]
    if not photo.filename:
        return jsonify({"error": "写真が選択されていません"}), 400

    try:
        image_block, raw_bytes, ext = image_to_content_block(photo)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    # 保存(あとで見返せるように)
    saved_name = f"{uuid.uuid4().hex}{ext}"
    with open(os.path.join(UPLOAD_DIR, saved_name), "wb") as f:
        f.write(raw_bytes)

    try:
        response = client.messages.create(
            model="claude-opus-4-8",
            max_tokens=2000,
            system=SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": [
                        image_block,
                        {"type": "text", "text": "この商品写真から出品情報を生成してください。"},
                    ],
                }
            ],
            output_config={"format": {"type": "json_schema", "schema": OUTPUT_SCHEMA}},
        )
    except anthropic.APIStatusError as e:
        return jsonify({"error": f"AI呼び出しでエラーが発生しました: {e.message}"}), 502
    except anthropic.APIConnectionError:
        app.logger.exception("APIConnectionError の詳細")
        return jsonify({"error": "AIサーバーへの接続に失敗しました。もう一度お試しください。"}), 502
    except anthropic.APIError as e:
        app.logger.exception("APIError の詳細")
        return jsonify({"error": f"AI呼び出しでエラーが発生しました: {e}"}), 502

    text = next((b.text for b in response.content if b.type == "text"), None)
    if not text:
        return jsonify({"error": "AIからの応答が空でした"}), 502

    try:
        result = json.loads(text)
    except json.JSONDecodeError:
        return jsonify({"error": "AI応答の解析に失敗しました"}), 502

    result["image_url"] = f"/uploads/{saved_name}"
    return jsonify(result)


@app.errorhandler(500)
def handle_internal_error(e):
    return jsonify({"error": "サーバーで予期しないエラーが発生しました。もう一度お試しください。"}), 500


@app.route("/uploads/<path:filename>")
def uploaded_file(filename):
    from flask import send_from_directory

    return send_from_directory(UPLOAD_DIR, filename)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    app.run(host="0.0.0.0", port=port, debug=debug)

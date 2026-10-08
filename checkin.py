import os
import time
import json
import hmac
import hashlib
import requests

PROFILES_JSON = os.getenv("PROFILES_JSON")
DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK")
DISCORD_USER_ID = os.getenv("DISCORD_USER_ID", "")

URL_DICT = {
    "Endfield": "https://zonai.skport.com/web/v1/game/endfield/attendance",
    "RefreshAuth": "https://zonai.skport.com/web/v1/auth/refresh",
}

BASE_HEADERS = {
    "Accept": "*/*",
    "Accept-Encoding": "gzip, deflate, br, zstd",
    "Content-Type": "application/json",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:147.0) Gecko/20100101 Firefox/147.0",
    "Referer": "https://game.skport.com/",
    "Origin": "https://game.skport.com",
    "platform": "3",
    "vName": "1.0.0",
    "dId": "",
    "Connection": "keep-alive"
}

def generate_sign(path, method, headers, query, body, sign_token):
    string_to_sign = path + (query if method == "GET" else body)
    if "timestamp" in headers:
        string_to_sign += str(headers["timestamp"])
    
    header_obj = {
        "platform": headers.get("platform", "3"),
        "timestamp": headers.get("timestamp", ""),
        "dId": headers.get("dId", ""),
        "vName": headers.get("vName", "1.0.0")
    }
    string_to_sign += json.dumps(header_obj, separators=(',', ':'))
    
    hmac_digest = hmac.new(sign_token.encode("utf-8"), string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()
    return hashlib.md5(hmac_digest.encode("utf-8")).hexdigest()

def refresh_sign_token(cred):
    headers = BASE_HEADERS.copy()
    headers["cred"] = cred
    headers["Cookie"] = f"SK_OAUTH_CRED_KEY={cred}"
    headers["timestamp"] = str(int(time.time()))
    try:
        res = requests.get(URL_DICT["RefreshAuth"], headers=headers, timeout=10).json()
        if res.get("code") == 0 and res.get("data", {}).get("token"):
            return res["data"]["token"]
    except Exception as e:
        print(f"Lỗi khi refresh token: {e}")
    return None

def auto_sign_profile(profile):
    cred = profile.get("SK_OAUTH_CRED_KEY")
    role_id = profile.get("id")
    server = profile.get("server", "2")
    lang = profile.get("language", "en")
    
    # Ưu tiên lấy token mới từ API refresh, nếu có sẵn SK_TOKEN_CACHE_KEY trong JSON thì dùng làm dự phòng
    sign_token = refresh_sign_token(cred) or profile.get("SK_TOKEN_CACHE_KEY")
    if not sign_token:
        return "💔 Arknights Endfield: Cookie tạch rùi 🥺"

    path = "/web/v1/game/endfield/attendance"
    timestamp = str(int(time.time()))
    
    headers = BASE_HEADERS.copy()
    headers.update({
        "cred": cred,
        "Cookie": f"SK_OAUTH_CRED_KEY={cred}",
        "sk-game-role": f"3_{role_id}_{server}",
        "sk-language": lang,
        "timestamp": timestamp
    })
    headers["sign"] = generate_sign(path, "POST", headers, "", "", sign_token)
    
    try:
        res = requests.post(URL_DICT["Endfield"], headers=headers, data="", timeout=10).json()
        code = res.get("code")
        msg = res.get("message", "")
        
        if code == 10000:
            return "💔 Arknights Endfield: Cookie tạch rùi 🥺"
        elif code == 0:
            return "💕 Arknights Endfield: Đã điểm danh nhận quà! (๑˃̵ᴗ˂̵)ﻭ"
        elif "Please do not sign in again" in msg:
            return "💕 Arknights Endfield: Quà đã nhận rồi! (¬_¬)♡"
        else:
            return f"💔 Arknights Endfield: Lỗi rùi ({msg}) ( • ᴖ • )"
    except Exception as e:
        return f"💔 Arknights Endfield: Lỗi rùi ({e}) ( • ᴖ • )"

def send_discord(content):
    if not DISCORD_WEBHOOK:
        return
    final_msg = ""
    if DISCORD_USER_ID:
        final_msg += f"<@{DISCORD_USER_ID}>\n"
    final_msg += "🎀 THÔNG BÁO ĐIỂM DANH 🎀\n"
    final_msg += content
    requests.post(DISCORD_WEBHOOK, json={"content": final_msg}, timeout=10)

def main():
    if not PROFILES_JSON:
        print("Thiếu biến môi trường PROFILES_JSON.")
        return
    profiles = json.loads(PROFILES_JSON)
    messages = [auto_sign_profile(p) for p in profiles]
    output_text = "\n".join(messages)
    print(output_text)
    send_discord(output_text)

if __name__ == "__main__":
    main()

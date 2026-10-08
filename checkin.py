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
    "GrantOAuth": "https://as.gryphline.com/user/oauth2/v2/grant",
    "GenCred": "https://zonai.skport.com/web/v1/user/auth/generate_cred_by_code"
}

BASE_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Content-Type": "application/json",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:147.0) Gecko/20100101 Firefox/147.0",
    "Referer": "https://game.skport.com/",
    "Origin": "https://game.skport.com",
    "platform": "3",
    "vName": "1.0.0",
    "dId": ""
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
    headers["timestamp"] = str(int(time.time()))
    try:
        res = requests.get(URL_DICT["RefreshAuth"], headers=headers, timeout=10).json()
        if res.get("code") == 0 and res.get("data", {}).get("token"):
            return res["data"]["token"]
    except Exception as e:
        print(f"Lỗi refresh token: {e}")
    return None

def auto_sign_profile(profile):
    account_name = profile.get("accountName", "Unknown")
    cred = profile.get("SK_OAUTH_CRED_KEY")
    role_id = profile.get("id")
    server = profile.get("server", "2")
    lang = profile.get("language", "en")
    
    sign_token = refresh_sign_token(cred)
    if not sign_token:
        return f"💔 [{account_name}] Arknights Endfield: Cookie/Cred tạch rùi (User not login) 🥺"

    path = "/web/v1/game/endfield/attendance"
    timestamp = str(int(time.time()))
    
    headers = BASE_HEADERS.copy()
    headers.update({
        "cred": cred,
        "sk-game-role": f"3_{role_id}_{server}",
        "sk-language": lang,
        "timestamp": timestamp
    })
    headers["sign"] = generate_sign(path, "POST", headers, "", "", sign_token)
    
    try:
        res = requests.post(URL_DICT["Endfield"], headers=headers, data="", timeout=10).json()
        code = res.get("code")
        msg = res.get("message", "")
        
        if code == 0:
            return f"💕 [{account_name}] Arknights Endfield: Đã điểm danh nhận quà! (๑˃̵ᴗ˂̵)ﻭ"
        elif "Please do not sign in again" in msg:
            return f"💕 [{account_name}] Arknights Endfield: Hôm nay đã nhận quà rồi! (¬_¬)♡"
        else:
            return f"💔 [{account_name}] Arknights Endfield: Lỗi ({msg}) ( • ᴖ • )"
    except Exception as e:
        return f"💔 [{account_name}] Arknights Endfield: Lỗi kết nối ({e})"

def send_discord(content):
    if not DISCORD_WEBHOOK:
        return
    msg = ""
    if DISCORD_USER_ID:
        msg += f"<@{DISCORD_USER_ID}>\n"
    msg += f"🎀 THÔNG BÁO ĐIỂM DANH SKPORT 🎀\n{content}"
    requests.post(DISCORD_WEBHOOK, json={"content": msg}, timeout=10)

def main():
    if not PROFILES_JSON:
        print("Thiếu biến môi trường PROFILES_JSON.")
        return
    profiles = json.loads(PROFILES_JSON)
    results = [auto_sign_profile(p) for p in profiles]
    output_text = "\n".join(results)
    print(output_text)
    send_discord(output_text)

if __name__ == "__main__":
    main()

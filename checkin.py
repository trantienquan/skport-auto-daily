import os
import time
import json
import hmac
import hashlib
import requests

PROFILES_JSON = os.getenv("PROFILES_JSON")
DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK")
DISCORD_USER_ID = os.getenv("DISCORD_USER_ID", "")

SESSION_FILE = "session.json"

URL_DICT = {
    "Endfield": "https://zonai.skport.com/web/v1/game/endfield/attendance",
    "Login": "https://as.gryphline.com/user/info/v1/login_by_password",
    "GrantOAuth": "https://as.gryphline.com/user/oauth2/v2/grant",
    "GenCred": "https://zonai.skport.com/web/v1/user/auth/generate_cred_by_code"
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

def load_session():
    if os.path.exists(SESSION_FILE):
        try:
            with open(SESSION_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_session(data):
    try:
        with open(SESSION_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Lỗi khi lưu file session: {e}")

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

def auto_login_with_password(email, password):
    try:
        login_res = requests.post(
            URL_DICT["Login"],
            json={"account": email, "password": password},
            headers={"Content-Type": "application/json", "User-Agent": BASE_HEADERS["User-Agent"]},
            timeout=10
        ).json()
        
        if login_res.get("status") != 0:
            print(f"Lỗi đăng nhập API: {login_res}")
            return None, None
            
        account_token = login_res.get("data", {}).get("token")
        
        grant_res = requests.post(
            URL_DICT["GrantOAuth"],
            json={"token": account_token, "appCode": "6eb76d4e13aa36e6", "type": 0},
            headers={"Content-Type": "application/json"},
            timeout=10
        ).json()
        
        oauth_code = grant_res.get("data", {}).get("code")
        
        cred_res = requests.post(
            URL_DICT["GenCred"],
            json={"code": oauth_code, "kind": 1},
            headers=BASE_HEADERS,
            timeout=10
        ).json()
        
        new_cred = cred_res.get("data", {}).get("cred")
        new_sign_token = cred_res.get("data", {}).get("token")
        
        return new_cred, new_sign_token
    except Exception as e:
        print(f"Lỗi Auto-Login: {e}")
        return None, None

def execute_attendance(cred, sign_token, role_id, server, lang):
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
    
    return requests.post(URL_DICT["Endfield"], headers=headers, data="", timeout=10).json()

def process_profile(profile, session_data):
    account_name = profile.get("accountName", "Unknown")
    role_id = str(profile.get("id"))
    server = profile.get("server", "2")
    lang = profile.get("language", "en")
    
    email = profile.get("email")
    password = profile.get("password")
    
    user_session = session_data.get(role_id, {})
    cred = user_session.get("cred") or profile.get("SK_OAUTH_CRED_KEY")
    sign_token = user_session.get("sign_token") or profile.get("SK_TOKEN_CACHE_KEY")
    
    if cred and sign_token:
        try:
            res = execute_attendance(cred, sign_token, role_id, server, lang)
            code = res.get("code")
            msg = res.get("message", "")
            
            if code == 0:
                return f"💕 [{account_name}] Arknights Endfield: Đã điểm danh nhận quà! (๑˃̵ᴗ˂̵)ﻭ"
            elif "Please do not sign in again" in msg or "already" in msg.lower():
                return f"💕 [{account_name}] Arknights Endfield: Quà đã nhận rồi! (¬_¬)♡"
            elif code != 10000 and "not log" not in msg.lower():
                return f"💔 [{account_name}] Arknights Endfield: Lỗi rùi ({msg}) ( • ᴖ • )"
        except Exception as e:
            return f"💔 [{account_name}] Lỗi kết nối ({e})"
            
    if not email or not password:
        return f"💔 [{account_name}] Cookie hết hạn và không có Email/Pass trong cấu hình! 🥺"
        
    print(f"🔄 [{account_name}] Đang thử đăng nhập lại bằng Email/Pass...")
    new_cred, new_sign_token = auto_login_with_password(email, password)
    
    if new_cred and new_sign_token:
        session_data[role_id] = {
            "cred": new_cred,
            "sign_token": new_sign_token
        }
        try:
            res_retry = execute_attendance(new_cred, new_sign_token, role_id, server, lang)
            code_retry = res_retry.get("code")
            msg_retry = res_retry.get("message", "")
            
            if code_retry == 0:
                return f"💕 [{account_name}] Đã cấp lại Cookie & Điểm danh thành công! (๑˃̵ᴗ˂̵)ﻭ"
            elif "Please do not sign in again" in msg_retry or "already" in msg_retry.lower():
                return f"💕 [{account_name}] Đã cấp lại Cookie, Quà hôm nay đã nhận! (¬_¬)♡"
            else:
                return f"💔 [{account_name}] Lỗi sau khi cấp Cookie ({msg_retry}) ( • ᴖ • )"
        except Exception as e:
            return f"💔 [{account_name}] Lỗi mạng sau đăng nhập ({e})"
    else:
        return f"💔 [{account_name}] Cookie không hợp lệ và Đăng nhập tự động bị máy chủ chặn. Vui lòng cập nhật session.json! 🥺"

def send_discord(content):
    if not DISCORD_WEBHOOK:
        return
    final_msg = ""
    if DISCORD_USER_ID:
        final_msg += f"<@{DISCORD_USER_ID}>\n"
    final_msg += "🎀 THÔNG BÁO ĐIỂM DANH SKPORT 🎀\n"
    final_msg += content
    try:
        requests.post(DISCORD_WEBHOOK, json={"content": final_msg}, timeout=10)
    except Exception as e:
        print(f"Không gửi được Discord: {e}")

def main():
    if not PROFILES_JSON:
        print("Thiếu biến môi trường PROFILES_JSON.")
        return
    
    profiles = json.loads(PROFILES_JSON)
    session_data = load_session()
    
    messages = []
    for p in profiles:
        msg = process_profile(p, session_data)
        messages.append(msg)
        time.sleep(2)
        
    save_session(session_data)
    
    output_text = "\n".join(messages)
    print(output_text)
    send_discord(output_text)

if __name__ == "__main__":
    main()

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
    except Exception:
        pass
    return None

def auto_login_with_password(email, password):
    """Hàm tự động đăng nhập từ gốc lấy CRED mới nếu hệ thống không có Captcha"""
    try:
        # Bước 1: Gọi API Đăng nhập
        login_res = requests.post(
            URL_DICT["Login"],
            json={"account": email, "password": password},
            headers={"Content-Type": "application/json", "User-Agent": BASE_HEADERS["User-Agent"]},
            timeout=10
        ).json()
        
        if login_res.get("status") != 0:
            print(f"Login API failed: {login_res}")
            return None, None
            
        account_token = login_res.get("data", {}).get("token")
        
        # Bước 2: Xin quyền OAuth Code (appCode chuẩn của SKPort Web)
        grant_res = requests.post(
            URL_DICT["GrantOAuth"],
            json={"token": account_token, "appCode": "6eb76d4e13aa36e6", "type": 0},
            headers={"Content-Type": "application/json"},
            timeout=10
        ).json()
        
        oauth_code = grant_res.get("data", {}).get("code")
        
        # Bước 3: Đổi OAuth Code lấy CRED và Sign Token
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
        print(f"Lỗi quá trình Auto-Login: {e}")
        return None, None

def execute_attendance(account_name, cred, sign_token, role_id, server, lang):
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
    
    res = requests.post(URL_DICT["Endfield"], headers=headers, data="", timeout=10).json()
    return res

def auto_sign_profile(profile):
    account_name = profile.get("accountName", "Unknown")
    cred = profile.get("SK_OAUTH_CRED_KEY")
    role_id = profile.get("id")
    server = profile.get("server", "2")
    lang = profile.get("language", "en")
    
    email = profile.get("email")
    password = profile.get("password")
    
    # Ưu tiên làm mới token ký với chuỗi cred đang có
    sign_token = refresh_sign_token(cred) or profile.get("SK_TOKEN_CACHE_KEY")
    need_relogin = False
    
    if sign_token:
        try:
            # Thử điểm danh nghiệm thu
            res = execute_attendance(account_name, cred, sign_token, role_id, server, lang)
            code = res.get("code")
            msg = res.get("message", "")
            
            if code == 0:
                return f"💕 [{account_name}] Arknights Endfield: Đã điểm danh nhận quà! (๑˃̵ᴗ˂̵)ﻭ"
            elif "Please do not sign in again" in msg:
                return f"💕 [{account_name}] Arknights Endfield: Quà đã nhận rồi! (¬_¬)♡"
            elif code == 10000 or "not log" in msg.lower():
                need_relogin = True # Bị bắt lỗi hết hạn, chuyển sang luồng auto-login
            else:
                return f"💔 [{account_name}] Arknights Endfield: Lỗi rùi ({msg}) ( • ᴖ • )"
        except Exception as e:
            return f"💔 [{account_name}] Lỗi kết nối ({e})"
    else:
        need_relogin = True

    # Khởi chạy quy trình Auto-Login bằng Email/Pass
    if need_relogin:
        if not email or not password:
            return f"💔 [{account_name}] Cookie hết hạn & Không có cấu hình Email/Pass để tự đăng nhập 🥺"
            
        print(f"🔄 [{account_name}] Cookie hết hạn, đang tự động đăng nhập lại bằng Email...")
        new_cred, new_sign_token = auto_login_with_password(email, password)
        
        if new_cred and new_sign_token:
            try:
                # Thực hiện lại điểm danh với Credentials mới tinh
                res_retry = execute_attendance(account_name, new_cred, new_sign_token, role_id, server, lang)
                code_retry = res_retry.get("code")
                msg_retry = res_retry.get("message", "")
                
                if code_retry == 0:
                    return f"💕 [{account_name}] Tự động gia hạn Cookie & Điểm danh thành công! (๑˃̵ᴗ˂̵)ﻭ"
                elif "Please do not sign in again" in msg_retry:
                    return f"💕 [{account_name}] Tự gia hạn Cookie xong, Quà hôm nay đã nhận rồi! (¬_¬)♡"
                else:
                    return f"💔 [{account_name}] Lỗi sau khi gia hạn ({msg_retry}) ( • ᴖ • )"
            except Exception as e:
                return f"💔 [{account_name}] Lỗi mạng vòng 2 ({e})"
        else:
            return f"💔 [{account_name}] Đăng nhập tự động thất bại (Có thể do sai Pass, hoặc API yêu cầu mã hóa/Captcha) 🥺"

def send_discord(content):
    if not DISCORD_WEBHOOK:
        return
    final_msg = ""
    if DISCORD_USER_ID:
        final_msg += f"<@{DISCORD_USER_ID}>\n"
    final_msg += "🎀 THÔNG BÁO ĐIỂM DANH 🎀\n"
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
    messages = [auto_sign_profile(p) for p in profiles]
    output_text = "\n".join(messages)
    print(output_text)
    send_discord(output_text)

if __name__ == "__main__":
    main()

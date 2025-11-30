import json
import os
import threading

DATA_FILE = "user_data.json"
lock = threading.Lock()

def load_db():
    if not os.path.exists(DATA_FILE): return {}
    with open(DATA_FILE, "r") as f:
        try: return json.load(f)
        except: return {}

def save_db(data):
    with lock:
        with open(DATA_FILE, "w") as f:
            json.dump(data, f, indent=4)

def get_user_config(user_id):
    db = load_db()
    return db.get(str(user_id), {
        "api_key": None, "secret_key": None,
        "capital": 1000, "mode": "MANUAL", # AUTO or MANUAL
        "streak": 0, "last_result": "WIN" # WIN or LOSS
    })

def update_user_config(user_id, key, value):
    db = load_db()
    uid = str(user_id)
    if uid not in db: db[uid] = get_user_config(uid)
    db[uid][key] = value
    save_db(db)

def calculate_volume(user_id):
    """Tính toán Volume theo Logic Ngô Bằng"""
    cfg = get_user_config(user_id)
    capital = cfg['capital']
    streak = cfg['streak']
    last_res = cfg['last_result']
    
    # Logic Smart Martingale
    risk_pct = 0.5 # Default
    
    if last_res == "WIN":
        if streak == 0: risk_pct = 0.5
        elif streak == 1: risk_pct = 1.0
        elif streak == 2: risk_pct = 1.25
        else: risk_pct = 2.0
    else: # LOSS
        # Nếu vừa thua lệnh 0.5, gấp lên 1.0 để gỡ
        if streak == 0: risk_pct = 0.5 # Lệnh đầu thua
        elif streak == -1: risk_pct = 1.0 # Đang gỡ
        else: risk_pct = 0.5 # Thua tiếp hoặc gãy chuỗi -> Reset
    
    amount_usd = (capital * risk_pct) / 100
    return amount_usd, risk_pct

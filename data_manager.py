import json
import os

DATA_FILE = "user_data.json"

def load_data():
    if not os.path.exists(DATA_FILE):
        return {}
    try:
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    except:
        return {}

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=4)

def get_user(user_id):
    data = load_data()
    return data.get(str(user_id), {})

def update_user(user_id, key, value):
    data = load_data()
    user_id = str(user_id)
    if user_id not in data:
        data[user_id] = {
            "api_key": "", "secret_key": "", 
            "mode": "MANUAL", "capital": 1000, 
            "base_risk": 0.5, # % cơ bản
            "streak": 0, "last_result": "WIN" # Để tính toán vốn
        }
    data[user_id][key] = value
    save_data(data)

# Logic quản lý vốn đặc biệt của Ngô Bằng
def calculate_position_size(user_id):
    user = get_user(user_id)
    base_risk = user.get("base_risk", 0.5)
    streak = user.get("streak", 0)
    last_res = user.get("last_result", "WIN")
    capital = user.get("capital", 1000)

    # Logic: 0.5% -> Thắng -> 1% -> Thắng -> 1.25% -> Max 2%
    # Thua 0.5% -> 1%. Thua 1% -> Về 0.5%
    
    risk_percent = base_risk # Mặc định 0.5%

    if last_res == "WIN":
        if streak == 0: risk_percent = 0.5
        elif streak == 1: risk_percent = 1.0
        elif streak == 2: risk_percent = 1.25
        else: risk_percent = 2.0 # Max
    else: # LOSS
        if streak == 1: # Vừa thua lệnh đầu 0.5%
            risk_percent = 1.0 # Gấp lên gỡ
        else:
            risk_percent = 0.5 # Thua tiếp thì về lại mức thấp nhất

    return (capital * risk_percent) / 100

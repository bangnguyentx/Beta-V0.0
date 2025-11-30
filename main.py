import os
import asyncio
import threading
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, CallbackQueryHandler, MessageHandler, filters
import ccxt
import nest_asyncio

# Import modules
from storage import update_user_config, get_user_config, calculate_volume, load_db
from analysis import get_market_signal

# --- CONFIG ---
TOKEN = "8548469595:AAFYg640srzQFpKPjOVMYYf1drL-kb11e28" # Token của bạn
SYMBOL = "BTC/USDT"
nest_asyncio.apply()

# --- FLASK SERVER (KEEP ALIVE) ---
app = Flask(__name__)
@app.route('/')
def home(): return "<h1>Ngo Bang Bot is Alive!</h1>"

def run_web():
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))

# --- TRADING EXECUTION ---
async def execute_order(user_id, signal, price):
    cfg = get_user_config(user_id)
    if not cfg['api_key'] or not cfg['secret_key']: return "⚠️ Chưa nhập API Key"
    
    volume_usd, risk_pct = calculate_volume(user_id)
    amount_coin = volume_usd / price
    
    try:
        # Kết nối API User
        exchange = ccxt.binance({
            'apiKey': cfg['api_key'],
            'secret': cfg['secret_key'],
            'options': {'defaultType': 'future'}
        })
        
        # Đặt lệnh thật (Demo thì comment dòng này lại)
        # side = 'buy' if signal == 'BUY' else 'sell'
        # order = exchange.create_market_order(SYMBOL, side, amount_coin)
        
        # Giả lập kết quả để test logic vốn
        return f"✅ Đã vào lệnh {signal}\n💰 Vốn: {volume_usd:.2f}$ ({risk_pct}%)\n📈 Giá: {price}"
        
    except Exception as e:
        return f"❌ Lỗi sàn: {str(e)}"

# --- TELEGRAM HANDLERS ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = (f"👋 Chào {user.first_name}!\n"
            "Đây là **Ngo Bang Trading Bot (Ver Gen Z)**.\n"
            "Hệ thống tự động sử dụng thuật toán Gia tốc & RSI.")
    
    keyboard = [
        [InlineKeyboardButton("🔑 Nhập API Binance", callback_data="CMD_API")],
        [InlineKeyboardButton("💵 Cài đặt Vốn", callback_data="CMD_CAPITAL")],
        [InlineKeyboardButton("⚙️ Chế độ (Auto/Manual)", callback_data="CMD_MODE")],
        [InlineKeyboardButton("📊 Kiểm tra cấu hình", callback_data="CMD_CHECK")]
    ]
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    uid = query.from_user.id
    
    if data == "CMD_API":
        await query.message.reply_text("👉 Hãy gửi API theo cú pháp:\n`API_KEY|SECRET_KEY`", parse_mode='Markdown')
        context.user_data['action'] = 'WAIT_API'
        
    elif data == "CMD_CAPITAL":
        await query.message.reply_text("👉 Nhập tổng số vốn (USD) muốn bot quản lý (VD: 1000):")
        context.user_data['action'] = 'WAIT_CAPITAL'
        
    elif data == "CMD_MODE":
        kb = [
            [InlineKeyboardButton("🤖 AUTO (Tự động 100%)", callback_data="SET_MODE_AUTO")],
            [InlineKeyboardButton("fuck🕹 MANUAL (Duyệt tay)", callback_data="SET_MODE_MANUAL")]
        ]
        await query.message.reply_text("Chọn chế độ vận hành:", reply_markup=InlineKeyboardMarkup(kb))

    elif data.startswith("SET_MODE_"):
        mode = data.split("_")[2]
        update_user_config(uid, "mode", mode)
        await query.edit_message_text(f"✅ Đã chuyển sang chế độ: **{mode}**", parse_mode='Markdown')

    elif data == "CMD_CHECK":
        cfg = get_user_config(uid)
        vol, pct = calculate_volume(uid)
        msg = (f"📋 **CẤU HÌNH HIỆN TẠI**\n"
               f"• Vốn gốc: {cfg['capital']}$\n"
               f"• Chế độ: {cfg['mode']}\n"
               f"• API: {'✅ Đã nhập' if cfg['api_key'] else '❌ Chưa nhập'}\n"
               f"• Lệnh tiếp theo: {vol:.2f}$ ({pct}%)")
        await query.message.reply_text(msg, parse_mode='Markdown')
        
    # Xử lý nút duyệt lệnh tay
    elif data.startswith("TRADE_"):
        _, signal, price_str = data.split("_")
        res = await execute_order(uid, signal, float(price_str))
        await query.edit_message_text(res)

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    text = update.message.text
    action = context.user_data.get('action')
    
    if action == 'WAIT_API':
        if "|" in text:
            api, secret = text.split("|")
            update_user_config(uid, "api_key", api.strip())
            update_user_config(uid, "secret_key", secret.strip())
            await update.message.reply_text("✅ Đã lưu API Key thành công! Hãy xóa tin nhắn chứa key để bảo mật.")
            context.user_data['action'] = None
        else:
            await update.message.reply_text("❌ Sai cú pháp. Vui lòng thử lại.")
            
    elif action == 'WAIT_CAPITAL':
        if text.isdigit():
            update_user_config(uid, "capital", float(text))
            await update.message.reply_text(f"✅ Đã cập nhật vốn: {text}$")
            context.user_data['action'] = None

# --- BACKGROUND SCANNER ---
async def market_scanner(app):
    """Vòng lặp vô tận quét thị trường"""
    print("🚀 Scanner Started...")
    while True:
        # 1. Phân tích
        signal, price, info = get_market_signal(SYMBOL)
        
        if signal in ["BUY", "SELL"]:
            print(f"🔥 Signal Detected: {signal} at {price}")
            
            # 2. Lấy danh sách user
            users = load_db()
            for uid, cfg in users.items():
                if not cfg.get('api_key'): continue
                
                # Tính toán volume dự kiến
                vol, pct = calculate_volume(uid)
                msg_text = (f"⚡ **TÍN HIỆU {signal}**\n"
                            f"• Cặp: {SYMBOL}\n"
                            f"• Giá: {price}\n"
                            f"• Chỉ báo: {info}\n"
                            f"• Volume đề xuất: {vol:.2f}$ ({pct}%)")
                
                # 3. Xử lý theo chế độ
                if cfg['mode'] == 'AUTO':
                    res = await execute_order(uid, signal, price)
                    await app.bot.send_message(chat_id=uid, text=f"{msg_text}\n\n🤖 **AUTO:**\n{res}")
                else:
                    kb = [[InlineKeyboardButton(f"✅ Vào lệnh ({vol:.2f}$)", callback_data=f"TRADE_{signal}_{price}")]]
                    await app.bot.send_message(chat_id=uid, text=msg_text, reply_markup=InlineKeyboardMarkup(kb))
        
        await asyncio.sleep(15) # Nghỉ 15s

# --- MAIN ENTRY POINT ---
if __name__ == "__main__":
    # 1. Chạy Web Server (Thread riêng)
    threading.Thread(target=run_web).start()
    
    # 2. Setup Bot
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    
    # 3. Chạy Scanner + Bot Polling
    loop = asyncio.get_event_loop()
    loop.create_task(market_scanner(app))
    
    print("Bot is running...")
    app.run_polling()

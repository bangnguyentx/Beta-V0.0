import os
import threading
import time
import ccxt
import pandas as pd
import pandas_ta as ta
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters, CallbackQueryHandler
from data_manager import update_user, get_user, calculate_position_size, load_data

# --- CẤU HÌNH ---
TOKEN = "YOUR_TELEGRAM_BOT_TOKEN" # Thay Token bot của bạn vào đây
SYMBOL = "BTC/USDT"
TIMEFRAME = "15m"

# --- FLASK SERVER (Để Render không tắt Bot) ---
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot Trading Ngô Bằng is Running!"

def run_flask():
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)

# --- LOGIC TRADING (TỪ CÁC PHẦN TRƯỚC) ---
def fetch_and_calculate():
    # Dùng API Public của Binance để lấy giá (không cần key user đoạn này)
    ex_public = ccxt.binance() 
    try:
        bars = ex_public.fetch_ohlcv(SYMBOL, TIMEFRAME, limit=100)
        df = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        
        # Chỉ báo
        df['rsi'] = df.ta.rsi(length=14)
        bb = df.ta.bbands(length=20, std=2)
        df = pd.concat([df, bb], axis=1)
        
        # Gia tốc (Logic Ngô Bằng)
        df['delta'] = df['close'].diff()
        df['velocity'] = df['delta'].rolling(window=3).mean()
        df['accel'] = df['velocity'].diff()
        
        last = df.iloc[-1]
        
        # Logic Vào lệnh
        signal = "NEUTRAL"
        # MUA: RSI < 30 + Giá < LowerBand + Gia tốc dương
        if last['rsi'] < 30 and last['close'] < last['BBL_20_2.0'] and last['accel'] > 0:
            signal = "BUY"
        # BÁN: RSI > 70
        elif last['rsi'] > 70:
            signal = "SELL"
            
        return signal, last['close']
    except Exception as e:
        print(f"Lỗi data: {e}")
        return "ERROR", 0

# --- XỬ LÝ LỆNH CHO USER ---
async def execute_trade(app_context, signal, price):
    data = load_data()
    for user_id, info in data.items():
        if not info.get('api_key') or not info.get('secret_key'):
            continue
            
        mode = info.get('mode', 'MANUAL')
        amount_usd = calculate_position_size(user_id)
        amount_coin = amount_usd / price 

        # Gửi thông báo Tín hiệu
        msg = f"🚀 **TÍN HIỆU {signal}**\nCặp: {SYMBOL}\nGiá: {price}\n"
        
        if mode == 'AUTO':
            # Auto vào lệnh
            try:
                user_ex = ccxt.binance({
                    'apiKey': info['api_key'],
                    'secret': info['secret_key'],
                    'options': {'defaultType': 'future'}
                })
                # Demo lệnh (Thay create_market_buy_order để chạy thật)
                # order = user_ex.create_market_buy_order(SYMBOL, amount_coin) 
                msg += f"✅ Đã Auto vào lệnh: {amount_usd:.2f}$"
                
                # Cập nhật trạng thái thắng thua giả lập (Ở code thật phải check PnL)
                update_user(user_id, "streak", info.get("streak", 0) + 1) 
                
            except Exception as e:
                msg += f"❌ Lỗi vào lệnh: {str(e)}"
            await app_context.bot.send_message(chat_id=user_id, text=msg)
            
        else: # MANUAL
            # Gửi nút bấm
            keyboard = [[InlineKeyboardButton(f"Theo lệnh ({amount_usd:.2f}$)", callback_data=f"TRADE_{signal}_{amount_coin}")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await app_context.bot.send_message(chat_id=user_id, text=msg + "Chọn bên dưới để theo:", reply_markup=reply_markup)

# --- TELEGRAM HANDLERS ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reply_keyboard = [['🔑 Nhập API', '⚙️ Chỉnh Vốn'], ['🤖 Chế độ (Auto/Manual)', '📊 Xem cài đặt']]
    await update.message.reply_text(
        "👋 Chào mừng đến với Bot Trading Ngô Bằng!\nHệ thống giao dịch Crypto tự động Gen Z.",
        reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=False, resize_keyboard=True)
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.message.chat_id
    
    if text == '🔑 Nhập API':
        await update.message.reply_text("Vui lòng nhập theo cú pháp:\n`API KEY_CỦA_BẠN|SECRET_KEY_CỦA_BẠN`", parse_mode='Markdown')
        context.user_data['waiting_for_api'] = True
        
    elif "|" in text and context.user_data.get('waiting_for_api'):
        try:
            api, secret = text.split("|")
            update_user(user_id, "api_key", api.strip())
            update_user(user_id, "secret_key", secret.strip())
            context.user_data['waiting_for_api'] = False
            await update.message.reply_text("✅ Đã lưu API thành công!")
        except:
            await update.message.reply_text("❌ Sai cú pháp.")

    elif text == '⚙️ Chỉnh Vốn':
        await update.message.reply_text("Nhập số vốn (USD) muốn bot quản lý (VD: 1000):")
        context.user_data['waiting_for_capital'] = True
        
    elif text.isdigit() and context.user_data.get('waiting_for_capital'):
        update_user(user_id, "capital", float(text))
        context.user_data['waiting_for_capital'] = False
        await update.message.reply_text(f"✅ Đã set vốn: {text}$")

    elif text == '🤖 Chế độ (Auto/Manual)':
        keyboard = [
            [InlineKeyboardButton("Auto 100%", callback_data="MODE_AUTO")],
            [InlineKeyboardButton("Manual (Duyệt tay)", callback_data="MODE_MANUAL")]
        ]
        await update.message.reply_text("Chọn chế độ:", reply_markup=InlineKeyboardMarkup(keyboard))
        
    elif text == '📊 Xem cài đặt':
        user = get_user(user_id)
        msg = f"Vốn: {user.get('capital')}$\nMode: {user.get('mode')}\nLogic vốn: 0.5% -> 1% -> 1.25% -> 2%"
        await update.message.reply_text(msg)

async def button_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.message.chat_id
    data = query.data
    
    if "MODE_" in data:
        mode = data.split("_")[1]
        update_user(user_id, "mode", mode)
        await query.edit_message_text(f"✅ Đã chuyển sang chế độ: {mode}")
        
    elif "TRADE_" in data:
        # User bấm nút "Theo lệnh"
        _, signal, amount = data.split("_")
        user = get_user(user_id)
        
        try:
            # Thực hiện lệnh thật tại đây
            user_ex = ccxt.binance({
                'apiKey': user['api_key'], 'secret': user['secret_key'],
                'options': {'defaultType': 'future'}
            })
            # user_ex.create_market_order(SYMBOL, signal.lower(), float(amount)) # Uncomment để chạy thật
            await query.edit_message_text(f"✅ Đã khớp lệnh tay: {signal} - Volume: {float(amount):.4f} coin")
        except Exception as e:
            await query.edit_message_text(f"❌ Lỗi: {e}")

# --- LUỒNG QUÉT NẾN ---
def run_scanner(loop, app_context):
    print("Bot Scanner Started...")
    while True:
        # 1. Quét dữ liệu
        signal, price = fetch_and_calculate()
        
        # 2. Nếu có tín hiệu, đẩy task vào luồng Async của Telegram
        if signal in ["BUY", "SELL"]:
            print(f"Bắt được tín hiệu: {signal}")
            loop.create_task(execute_trade(app_context, signal, price))
            
        time.sleep(15) # Quét 15 giây một lần (4 lần/phút)

# --- MAIN ---
if __name__ == '__main__':
    # 1. Chạy Flask Server ở luồng riêng
    threading.Thread(target=run_flask).start()

    # 2. Khởi tạo Bot Telegram
    app_bot = ApplicationBuilder().token(TOKEN).build()
    
    app_bot.add_handler(CommandHandler("start", start))
    app_bot.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app_bot.add_handler(CallbackQueryHandler(button_click))

    # 3. Chạy luồng Scanner
    # Lấy event loop của bot để inject task
    loop = asyncio.get_event_loop()
    threading.Thread(target=run_scanner, args=(loop, app_bot)).start()

    print("Bot is polling...")
    app_bot.run_polling()

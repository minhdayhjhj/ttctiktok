
import sys
import os
import re
import json
import random
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime

import requests
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext

# Âm thanh: cố gắng dùng winsound (Windows). Nếu không có, thử playsound (pip install playsound).
AUDIO_AVAILABLE = False
USE_WINSOUND = False
try:
    import winsound
    AUDIO_AVAILABLE = True
    USE_WINSOUND = True
except Exception:
    try:
        from playsound import playsound
        AUDIO_AVAILABLE = True
        USE_WINSOUND = False
    except Exception:
        AUDIO_AVAILABLE = False

# ==========================
# Cấu hình & Hằng số
# ==========================

APP_NAME = "Khang Tool Ultra Pro Max GUI"
APP_VERSION = "12.0"
DEFAULT_TTC_HOST = "https://tuongtaccheo.com"
DEFAULT_TTC_HOME = f"{DEFAULT_TTC_HOST}/home.php"
DEFAULT_TTC_GETPOST = f"{DEFAULT_TTC_HOST}/kiemtien/getpost.php"
DEFAULT_TTC_NHAN_TIEN = f"{DEFAULT_TTC_HOST}/kiemtien/nhantien.php"
DEFAULT_TTC_REFERER = f"{DEFAULT_TTC_HOST}/kiemtien/"
GRAPH_ME = "https://graph.facebook.com/me"

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_4) AppleWebKit/605.1.15 Version/16.5 Safari/605.1.15",
    "Mozilla/5.0 (Linux; Android 13; Pixel 6) AppleWebKit/537.36 Chrome/124.0 Mobile Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64) AppleWebKit/537.36 Chrome/123.0 Safari/537.36",
]

MAX_RETRIES = 6
REQUEST_TIMEOUT = 15

# Điều tiết thông minh mặc định
BASE_DELAY = (5, 12)
BURST_LIMIT = 10
BURST_COOLDOWN = (22, 45)

# Turbo mode (an toàn)
TURBO_DELAY = (3, 7)
TURBO_BURST_LIMIT = 14
TURBO_COOLDOWN = (25, 55)

CONFIG_FILE = "khang_tool_config.json"
LOG_FILE = "khang_tool_log.txt"

ASCII_BANNER = r"""
  ___   _   _   ___   _   _   ___  
 / _ \ | | | | / _ \ | | | | / _ \ 
| | | || | | || | | || | | || | | |
| |_| || |_| || |_| || |_| || |_| |
 \___/  \___/  \___/  \___/  \___/ 
"""

# ==========================
# Data classes
# ==========================

@dataclass
class SessionConfig:
    cookie_ttc: str = ""
    token_fb: str = ""
    delay_min: int = BASE_DELAY[0]
    delay_max: int = BASE_DELAY[1]
    burst_limit: int = BURST_LIMIT
    cooldown_min: int = BURST_COOLDOWN[0]
    cooldown_max: int = BURST_COOLDOWN[1]
    proxy: str = ""
    turbo: bool = False
    theme: str = "Dark"  # Dark / Neon / Classic

    def to_dict(self):
        return {
            "cookie_ttc": self.cookie_ttc,
            "token_fb": self.token_fb,
            "delay_min": self.delay_min,
            "delay_max": self.delay_max,
            "burst_limit": self.burst_limit,
            "cooldown_min": self.cooldown_min,
            "cooldown_max": self.cooldown_max,
            "proxy": self.proxy,
            "turbo": self.turbo,
            "theme": self.theme,
        }

    @staticmethod
    def from_dict(d):
        return SessionConfig(
            cookie_ttc=d.get("cookie_ttc", ""),
            token_fb=d.get("token_fb", ""),
            delay_min=int(d.get("delay_min", BASE_DELAY[0])),
            delay_max=int(d.get("delay_max", BASE_DELAY[1])),
            burst_limit=int(d.get("burst_limit", BURST_LIMIT)),
            cooldown_min=int(d.get("cooldown_min", BURST_COOLDOWN[0])),
            cooldown_max=int(d.get("cooldown_max", BURST_COOLDOWN[1])),
            proxy=d.get("proxy", ""),
            turbo=bool(d.get("turbo", False)),
            theme=d.get("theme", "Dark"),
        )

# ==========================
# Logger
# ==========================

class FileLogger:
    def __init__(self, file_path=LOG_FILE):
        self.file_path = file_path
        self.lock = threading.Lock()

    def log(self, level, msg):
        line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [{level}] {msg}"
        with self.lock:
            with open(self.file_path, "a", encoding="utf-8") as f:
                f.write(line + "\n")

# ==========================
# Core client
# ==========================

class TTCClient:
    def __init__(self, cfg: SessionConfig, logger: FileLogger):
        self.cfg = cfg
        self.logger = logger
        self.session = requests.Session()
        self._refresh_headers()

    def _get_proxies(self):
        if self.cfg.proxy.strip():
            return {"http": self.cfg.proxy.strip(), "https": self.cfg.proxy.strip()}
        return None

    def _refresh_headers(self):
        ua = random.choice(USER_AGENTS)
        self.headers_login = {
            "Host": "tuongtaccheo.com",
            "user-agent": ua,
            "cookie": self.cfg.cookie_ttc,
        }
        self.headers_work = {
            "Host": "tuongtaccheo.com",
            "user-agent": ua,
            "x-requested-with": "XMLHttpRequest",
            "referer": DEFAULT_TTC_REFERER,
            "cookie": self.cfg.cookie_ttc,
        }
        self.headers_claim = {
            "Host": "tuongtaccheo.com",
            "user-agent": ua,
            "x-requested-with": "XMLHttpRequest",
            "origin": DEFAULT_TTC_HOST,
            "referer": DEFAULT_TTC_REFERER,
            "cookie": self.cfg.cookie_ttc,
        }
        self.headers_fb = {"user-agent": ua}

    def _request(self, method, url, **kwargs):
        proxies = self._get_proxies()
        kwargs.setdefault("timeout", REQUEST_TIMEOUT)
        if proxies:
            kwargs.setdefault("proxies", proxies)

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                resp = self.session.request(method, url, **kwargs)
                if 200 <= resp.status_code < 300:
                    return resp
                self.logger.log("WARN", f"HTTP {resp.status_code} cho {url} (lần {attempt}/{MAX_RETRIES})")
            except requests.RequestException as e:
                self.logger.log("ERROR", f"Lỗi kết nối {url}: {e} (lần {attempt}/{MAX_RETRIES})")
            time.sleep(min(2 * attempt, 8))
        raise RuntimeError(f"Lỗi khi gọi {url} sau {MAX_RETRIES} lần thử")

    def check_token(self):
        params = {"access_token": self.cfg.token_fb}
        resp = self._request("GET", GRAPH_ME, headers=self.headers_fb, params=params)
        try:
            j = resp.json()
        except Exception:
            j = {}
        if "id" in j:
            return True, j.get("name", "Unknown")
        err = j.get("error", {}).get("message") if isinstance(j, dict) else resp.text
        return False, err

    def get_balance(self):
        resp = self._request("GET", DEFAULT_TTC_HOME, headers=self.headers_login)
        text = resp.text
        m = re.search(r'soduchinh">\s*([^<]+)</strong>', text)
        if not m:
            raise ValueError("Không lấy được số dư. Cookie có thể hết hạn hoặc thay đổi giao diện.")
        return m.group(1).strip()

    def get_next_post_id(self):
        resp = self._request("GET", DEFAULT_TTC_GETPOST, headers=self.headers_work)
        text = resp.text
        m = re.search(r'"idpost":"(\d+)"', text)
        if not m:
            return None, text
        return m.group(1), text

    def like_on_facebook(self, post_id: str):
        url = f"https://graph.facebook.com/{post_id}/likes"
        data = {"access_token": self.cfg.token_fb}
        resp = self._request("POST", url, headers=self.headers_fb, data=data)
        try:
            return resp.json()
        except Exception:
            return {"raw": resp.text, "status_code": resp.status_code}

    def claim_reward(self, post_id: str):
        data = {"id": post_id}
        resp = self._request("POST", DEFAULT_TTC_NHAN_TIEN, headers=self.headers_claim, data=data)
        try:
            return resp.json()
        except Exception:
            return {"raw": resp.text, "status_code": resp.status_code}

# ==========================
# Worker thread (Full Auto)
# ==========================

class LikeWorker(threading.Thread):
    def __init__(self, client: TTCClient, ui_cb, cfg: SessionConfig, logger: FileLogger):
        super().__init__(daemon=True)
        self.client = client
        self.ui_cb = ui_cb
        self.cfg = cfg
        self.logger = logger
        self.stop_signal = threading.Event()
        self.paused = threading.Event()
        self.burst_count = 0

    def stop(self):
        self.stop_signal.set()

    def pause(self):
        self.paused.set()

    def resume(self):
        self.paused.clear()

    def _sleep_progress(self, seconds, reason):
        self.ui_cb("info", f"[{reason}] nghỉ {seconds}s")
        for _ in range(seconds):
            if self.stop_signal.is_set():
                return
            time.sleep(1)

    def _current_delays(self):
        if self.cfg.turbo:
            return (max(1, self.cfg.delay_min or TURBO_DELAY[0]),
                    max(2, self.cfg.delay_max or TURBO_DELAY[1]),
                    max(1, self.cfg.burst_limit or TURBO_BURST_LIMIT),
                    max(5, self.cfg.cooldown_min or TURBO_COOLDOWN[0]),
                    max(6, self.cfg.cooldown_max or TURBO_COOLDOWN[1]))
        return (self.cfg.delay_min, self.cfg.delay_max,
                self.cfg.burst_limit, self.cfg.cooldown_min, self.cfg.cooldown_max)

    def _notify_claim(self):
        if not AUDIO_AVAILABLE:
            return
        try:
            if USE_WINSOUND:
                winsound.Beep(1000, 250)  # 0.25s beep
                winsound.Beep(1400, 180)  # 0.18s beep
            else:
                # playsound sẽ phát file nếu có, ở đây dùng tone mặc định không có sẵn
                # Bạn có thể đặt file "success.mp3" cùng thư mục và bật dòng dưới:
                # playsound("success.mp3")
                pass
        except Exception as e:
            self.ui_cb("warn", f"Âm thanh lỗi: {e}")

    def run(self):
        self.ui_cb("status", "Đang chạy nhiệm vụ (Full Auto)...")
        while not self.stop_signal.is_set():
            if self.paused.is_set():
                time.sleep(0.3)
                continue

            try:
                # Đổi UA theo nhịp
                if random.random() < 0.18:
                    self.client._refresh_headers()

                post_id, raw = self.client.get_next_post_id()
                if not post_id:
                    self.ui_cb("warn", "Hết nhiệm vụ hoặc bị hạn chế tạm thời.")
                    self._sleep_progress(random.randint(18, 32), "no_job")
                    continue

                self.ui_cb("info", f"Đang like ID: {post_id}")

                like_result = self.client.like_on_facebook(post_id)
                self.logger.log("INFO", f"Like {post_id} => {like_result}")

                if isinstance(like_result, dict) and like_result.get("success") is True:
                    self.ui_cb("ok", f"Like thành công: {post_id}")
                else:
                    self.ui_cb("warn", f"Kết quả like chưa rõ: {like_result}")

                claim_result = self.client.claim_reward(post_id)
                self.logger.log("INFO", f"Claim {post_id} => {claim_result}")
                msg = claim_result.get("msg") or claim_result.get("message") or str(claim_result)
                self.ui_cb("ok", f"Nhận xu: {msg}")

                # Âm thanh khi claim thành công
                self._notify_claim()

                # Cập nhật số dư ngẫu nhiên
                if random.random() < 0.35:
                    try:
                        bal = self.client.get_balance()
                        self.ui_cb("balance", f"Số dư: {bal}")
                    except Exception as e:
                        self.ui_cb("warn", f"Không cập nhật số dư: {e}")

                # Điều tiết nhịp
                dmin, dmax, blimit, cdmin, cdmax = self._current_delays()
                self.burst_count += 1
                if self.burst_count >= blimit:
                    self.ui_cb("info", f"Burst đạt {self.burst_count}. Nghỉ dài an toàn.")
                    self.burst_count = 0
                    self._sleep_progress(random.randint(cdmin, cdmax), "cooldown")
                else:
                    self._sleep_progress(random.randint(dmin, dmax), "delay")

            except Exception as e:
                self.logger.log("ERROR", f"Lỗi vòng lặp: {e}")
                self.ui_cb("error", f"Lỗi vòng lặp: {e}")
                self._sleep_progress(random.randint(8, 16), "error")

        self.ui_cb("status", "Đã dừng nhiệm vụ.")

# ==========================
# GUI App (Custom Tkinter + ASCII Banner + Themes)
# ==========================

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"{APP_NAME} v{APP_VERSION}")
        self.geometry("1000x700")
        self.minsize(960, 640)

        self.style = ttk.Style(self)
        try:
            self.style.theme_use("clam")
        except:
            pass

        self.logger = FileLogger(LOG_FILE)
        self.cfg = self._load_config()

        self._build_theme(self.cfg.theme)
        self.client = TTCClient(self.cfg, self.logger)

        self.worker = None

        self._build_ui()

    # Theme builder
    def _build_theme(self, theme_name: str):
        self.cfg.theme = theme_name
        if theme_name == "Dark":
            primary = "#0c0f1a"; card = "#12162a"; accent = "#23294a"; text = "#dfe6e9"; hi = "#69f0ae"
        elif theme_name == "Neon":
            primary = "#000000"; card = "#0b0b0b"; accent = "#00ffcc"; text = "#39ff14"; hi = "#ffea00"
        else:  # Classic
            primary = "#f0f0f0"; card = "#ffffff"; accent = "#d0d0d0"; text = "#000000"; hi = "#1a73e8"

        self.configure(bg=primary)
        self.style.configure("TLabel", background=primary, foreground=text, font=("Consolas", 11))
        self.style.configure("Card.TLabelframe", background=card, foreground=text, font=("Consolas", 12, "bold"))
        self.style.configure("Card.TLabelframe.Label", background=card, foreground=text, font=("Consolas", 12, "bold"))
        self.style.configure("TEntry", fieldbackground=("#0f1324" if theme_name != "Classic" else "#ffffff"), foreground=(text if theme_name != "Classic" else "#000000"))
        self.style.configure("TButton", background=accent, foreground=(text if theme_name != "Classic" else "#000000"), font=("Consolas", 11, "bold"))
        self.style.map("TButton", background=[("active", "#30365e" if theme_name != "Classic" else "#b0b0b0")], foreground=[("active", "#ffffff" if theme_name != "Classic" else "#000000")])
        self.style.configure("TCheckbutton", background=primary, foreground=text)

        # lưu lại màu cho log
        self._theme_colors = {"primary": primary, "card": card, "accent": accent, "text": text, "hi": hi}

    def _build_ui(self):
        # Header với ASCII banner + chọn theme
        header = tk.Frame(self, bg=self._theme_colors["primary"])
        header.pack(fill="x", padx=12, pady=(8, 6))

        banner_box = tk.Text(header, height=7, bg=self._theme_colors["primary"], fg=self._theme_colors["hi"], bd=0, highlightthickness=0, font=("Consolas", 12, "bold"))
        banner_box.insert("end", ASCII_BANNER)
        banner_box.config(state="disabled")
        banner_box.pack(fill="x")

        title_bar = tk.Frame(header, bg=self._theme_colors["primary"])
        title_bar.pack(fill="x")
        tk.Label(title_bar, text=f"{APP_NAME} v{APP_VERSION}", bg=self._theme_colors["primary"], fg=self._theme_colors["hi"], font=("Consolas", 16, "bold")).pack(side="left")

        # Theme selector
        tk.Label(title_bar, text="Theme:", bg=self._theme_colors["primary"], fg=self._theme_colors["text"]).pack(side="left", padx=(12, 6))
        self.theme_var = tk.StringVar(value=self.cfg.theme)
        theme_combo = ttk.Combobox(title_bar, textvariable=self.theme_var, values=["Dark", "Neon", "Classic"], width=10)
        theme_combo.pack(side="left")
        ttk.Button(title_bar, text="Áp dụng", command=self.apply_theme).pack(side="left", padx=6)

        ttk.Button(title_bar, text="Lưu cấu hình", command=self._save_config).pack(side="right", padx=6)
        ttk.Button(title_bar, text="Tải cấu hình", command=self._reload_config).pack(side="right", padx=6)
        ttk.Button(title_bar, text="Mở log", command=self._open_log).pack(side="right", padx=6)

        # Split main
        main = tk.PanedWindow(self, orient="horizontal", sashrelief="raised", bg=self._theme_colors["primary"])
        main.pack(fill="both", expand=True, padx=12, pady=8)

        # Left panel: Config
        left = ttk.Labelframe(main, text="Cấu hình phiên", style="Card.TLabelframe")
        main.add(left, minsize=440)

        # Cookie & Token
        ttk.Label(left, text="Cookie TTC:").grid(row=0, column=0, sticky="w", padx=8, pady=6)
        self.ent_cookie = ttk.Entry(left, width=54)
        self.ent_cookie.grid(row=0, column=1, sticky="we", padx=8, pady=6)
        self.ent_cookie.insert(0, self.cfg.cookie_ttc)

        ttk.Label(left, text="Token Facebook:").grid(row=1, column=0, sticky="w", padx=8, pady=6)
        self.ent_token = ttk.Entry(left, width=54)
        self.ent_token.grid(row=1, column=1, sticky="we", padx=8, pady=6)
        self.ent_token.insert(0, self.cfg.token_fb)

        # Delay & Burst
        ttk.Label(left, text="Delay min (s):").grid(row=2, column=0, sticky="w", padx=8, pady=6)
        self.ent_dmin = ttk.Entry(left, width=10)
        self.ent_dmin.grid(row=2, column=1, sticky="w", padx=8, pady=6)
        self.ent_dmin.insert(0, str(self.cfg.delay_min))

        ttk.Label(left, text="Delay max (s):").grid(row=3, column=0, sticky="w", padx=8, pady=6)
        self.ent_dmax = ttk.Entry(left, width=10)
        self.ent_dmax.grid(row=3, column=1, sticky="w", padx=8, pady=6)
        self.ent_dmax.insert(0, str(self.cfg.delay_max))

        ttk.Label(left, text="Burst limit:").grid(row=4, column=0, sticky="w", padx=8, pady=6)
        self.ent_burst = ttk.Entry(left, width=10)
        self.ent_burst.grid(row=4, column=1, sticky="w", padx=8, pady=6)
        self.ent_burst.insert(0, str(self.cfg.burst_limit))

        ttk.Label(left, text="Cooldown min (s):").grid(row=5, column=0, sticky="w", padx=8, pady=6)
        self.ent_cdmin = ttk.Entry(left, width=10)
        self.ent_cdmin.grid(row=5, column=1, sticky="w", padx=8, pady=6)
        self.ent_cdmin.insert(0, str(self.cfg.cooldown_min))

        ttk.Label(left, text="Cooldown max (s):").grid(row=6, column=0, sticky="w", padx=8, pady=6)
        self.ent_cdmax = ttk.Entry(left, width=10)
        self.ent_cdmax.grid(row=6, column=1, sticky="w", padx=8, pady=6)
        self.ent_cdmax.insert(0, str(self.cfg.cooldown_max))

        ttk.Label(left, text="Proxy (tùy chọn):").grid(row=7, column=0, sticky="w", padx=8, pady=6)
        self.ent_proxy = ttk.Entry(left, width=54)
        self.ent_proxy.grid(row=7, column=1, sticky="we", padx=8, pady=6)
        self.ent_proxy.insert(0, self.cfg.proxy)

        self.var_turbo = tk.BooleanVar(value=self.cfg.turbo)
        ttk.Checkbutton(left, text="Turbo mode (an toàn)", variable=self.var_turbo).grid(row=8, column=0, columnspan=2, sticky="w", padx=8, pady=6)

        # Controls
        ctl = tk.Frame(left, bg=self._theme_colors["card"])
        ctl.grid(row=9, column=0, columnspan=2, sticky="we", padx=6, pady=10)
        self.btn_start = ttk.Button(ctl, text="Bắt đầu", command=self.start_worker)
        self.btn_start.pack(side="left", padx=6)
        self.btn_pause = ttk.Button(ctl, text="Tạm dừng", command=self.pause_worker, state="disabled")
        self.btn_pause.pack(side="left", padx=6)
        self.btn_resume = ttk.Button(ctl, text="Tiếp tục", command=self.resume_worker, state="disabled")
        self.btn_resume.pack(side="left", padx=6)
        self.btn_stop = ttk.Button(ctl, text="Dừng", command=self.stop_worker, state="disabled")
        self.btn_stop.pack(side="left", padx=6)

        # Right panel: Monitor
        right = ttk.Labelframe(main, text="Giám sát & Log", style="Card.TLabelframe")
        main.add(right)

        self.lbl_status = ttk.Label(right, text="Sẵn sàng.")
        self.lbl_status.pack(fill="x", padx=8, pady=(8, 4))

        bal_box = tk.Frame(right, bg=self._theme_colors["card"])
        bal_box.pack(fill="x", padx=8, pady=(4, 8))
        ttk.Label(bal_box, text="Số dư hiện tại:").pack(side="left")
        self.lbl_balance = ttk.Label(bal_box, text="N/A")
        self.lbl_balance.pack(side="left", padx=6)
        ttk.Button(bal_box, text="Cập nhật", command=self.update_balance).pack(side="right")
        ttk.Button(bal_box, text="Kiểm tra token", command=self.check_token).pack(side="right", padx=6)

        self.txt_log = scrolledtext.ScrolledText(
            right, height=22,
            bg=("#0f1324" if self.cfg.theme != "Classic" else "#ffffff"),
            fg=self._theme_colors["text"],
            insertbackground=self._theme_colors["text"],
            font=("Consolas", 11)
        )
        self.txt_log.pack(fill="both", expand=True, padx=8, pady=8)

        footer = tk.Frame(self, bg=self._theme_colors["primary"])
        footer.pack(fill="x", padx=12, pady=(4, 8))
        tk.Label(footer, text="Khang Tool • Ultra GUI + ASCII • Copilot", bg=self._theme_colors["primary"], fg="#a8b3bd" if self.cfg.theme != "Classic" else "#333333").pack(side="left")
        tk.Label(footer, text=f"Phiên bản {APP_VERSION}", bg=self._theme_colors["primary"], fg="#a8b3bd" if self.cfg.theme != "Classic" else "#333333").pack(side="right")

        # Full auto: tự động kiểm tra token + balance + chạy
        self.after(400, self.auto_bootstrap)

    # ==========================
    # UI helpers
    # ==========================

    def apply_theme(self):
        self._build_theme(self.theme_var.get())
        # Rebuild giao diện để áp theme (nhanh gọn: reload app)
        for w in list(self.children.values()):
            try:
                w.destroy()
            except Exception:
                pass
        self._build_ui()

    def ui_cb(self, kind, msg):
        color = {
            "info": "#82b1ff" if self.cfg.theme != "Classic" else "#1a73e8",
            "warn": "#ffd54f" if self.cfg.theme != "Classic" else "#f9ab00",
            "error": "#ff5252" if self.cfg.theme != "Classic" else "#d93025",
            "ok": "#69f0ae" if self.cfg.theme != "Classic" else "#188038",
            "status": "#80cbc4" if self.cfg.theme != "Classic" else "#1a73e8",
            "balance": "#b2ff59" if self.cfg.theme != "Classic" else "#188038",
        }.get(kind, self._theme_colors["text"])
        self.append_log(msg, color)
        if kind == "status":
            self.lbl_status.config(text=msg)
        if kind == "balance":
            self.lbl_balance.config(text=msg.replace("Số dư: ", ""))

    def append_log(self, msg, color):
        ts = datetime.now().strftime("%H:%M:%S")
        self.txt_log.insert("end", f"[{ts}] {msg}\n")
        start_index = f"{self.txt_log.index('end')} - {len(msg)+10}c"
        self.txt_log.tag_add(color, start_index, "end")
        self.txt_log.tag_config(color, foreground=color)
        self.txt_log.see("end")
        self.logger.log("LOG", msg)

    # ==========================
    # Actions
    # ==========================

    def auto_bootstrap(self):
        # Tự kiểm tra token + balance và tự chạy nếu ok
        try:
            self._sync_cfg_from_ui()  # lấy config hiện tại trước
        except Exception as e:
            self.append_log(f"Lỗi cấu hình: {e}", "#ff5252")
            return

        if not self.cfg.cookie_ttc or not self.cfg.token_fb:
            self.append_log("Thiếu Cookie TTC hoặc Token FB. Vui lòng nhập.", "#ffd54f")
            return

        ok, info = self.client.check_token()
        if not ok:
            self.append_log(f"Token không hợp lệ: {info}", "#ff5252")
            return
        self.append_log(f"Token hợp lệ. Người dùng: {info}", "#69f0ae")

        try:
            bal = self.client.get_balance()
            self.lbl_balance.config(text=bal)
            self.append_log(f"Số dư: {bal}", "#b2ff59")
        except Exception as e:
            self.append_log(f"Không lấy được số dư: {e}", "#ff5252")

        # Tự động start
        self.start_worker()

    def start_worker(self):
        try:
            self._sync_cfg_from_ui()
        except Exception as e:
            messagebox.showerror("Lỗi cấu hình", f"Giá trị không hợp lệ: {e}")
            return

        if not self.cfg.cookie_ttc or not self.cfg.token_fb:
            messagebox.showwarning("Thiếu thông tin", "Vui lòng nhập Cookie TTC và Token FB.")
            return

        # Kiểm tra token trước khi chạy (full auto bảo vệ)
        ok, info = self.client.check_token()
        if not ok:
            messagebox.showerror("Token không hợp lệ", f"Vui lòng kiểm tra lại token FB.\nChi tiết: {info}")
            return
        self.append_log(f"Token hợp lệ. Người dùng: {info}", "#69f0ae")

        # Test balance
        try:
            bal = self.client.get_balance()
            self.lbl_balance.config(text=bal)
            self.append_log(f"Số dư: {bal}", "#b2ff59")
        except Exception as e:
            self.append_log(f"Không lấy được số dư: {e}", "#ff5252")

        if self.worker and self.worker.is_alive():
            messagebox.showinfo("Đang chạy", "Worker đang chạy.")
            return

        self.worker = LikeWorker(self.client, self.ui_cb, self.cfg, self.logger)
        self.worker.start()

        self.btn_start.config(state="disabled")
        self.btn_pause.config(state="normal")
        self.btn_resume.config(state="disabled")
        self.btn_stop.config(state="normal")
        self.lbl_status.config(text="Đang chạy nhiệm vụ...")

    def pause_worker(self):
        if self.worker:
            self.worker.pause()
            self.btn_pause.config(state="disabled")
            self.btn_resume.config(state="normal")
            self.lbl_status.config(text="Tạm dừng...")

    def resume_worker(self):
        if self.worker:
            self.worker.resume()
            self.btn_pause.config(state="normal")
            self.btn_resume.config(state="disabled")
            self.lbl_status.config(text="Tiếp tục...")

    def stop_worker(self):
        if self.worker:
            self.worker.stop()
            self.worker.join(timeout=3)
            self.worker = None
            self.btn_start.config(state="normal")
            self.btn_pause.config(state="disabled")
            self.btn_resume.config(state="disabled")
            self.btn_stop.config(state="disabled")
            self.lbl_status.config(text="Đã dừng nhiệm vụ.")

    def update_balance(self):
        try:
            bal = self.client.get_balance()
            self.lbl_balance.config(text=bal)
            self.append_log(f"Số dư: {bal}", "#b2ff59")
        except Exception as e:
            self.append_log(f"Không lấy được số dư: {e}", "#ff5252")

    def check_token(self):
        ok, info = self.client.check_token()
        if ok:
            self.append_log(f"Token hợp lệ. Người dùng: {info}", "#69f0ae")
        else:
            self.append_log(f"Token lỗi: {info}", "#ff5252")
            messagebox.showerror("Token không hợp lệ", f"Vui lòng kiểm tra lại token FB.\nChi tiết: {info}")

    # ==========================
    # Config I/O
    # ==========================

    def _load_config(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return SessionConfig.from_dict(data)
            except Exception:
                pass
        return SessionConfig()

    def _save_config(self):
        try:
            self._sync_cfg_from_ui()
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(self.cfg.to_dict(), f, ensure_ascii=False, indent=2)
            messagebox.showinfo("Đã lưu", f"Đã lưu cấu hình vào {CONFIG_FILE}")
        except Exception as e:
            messagebox.showerror("Lỗi", f"Không thể lưu cấu hình: {e}")

    def _reload_config(self):
        self.cfg = self._load_config()
        self.ent_cookie.delete(0, "end"); self.ent_cookie.insert(0, self.cfg.cookie_ttc)
        self.ent_token.delete(0, "end"); self.ent_token.insert(0, self.cfg.token_fb)
        self.ent_dmin.delete(0, "end"); self.ent_dmin.insert(0, str(self.cfg.delay_min))
        self.ent_dmax.delete(0, "end"); self.ent_dmax.insert(0, str(self.cfg.delay_max))
        self.ent_burst.delete(0, "end"); self.ent_burst.insert(0, str(self.cfg.burst_limit))
        self.ent_cdmin.delete(0, "end"); self.ent_cdmin.insert(0, str(self.cfg.cooldown_min))
        self.ent_cdmax.delete(0, "end"); self.ent_cdmax.insert(0, str(self.cfg.cooldown_max))
        self.var_turbo.set(self.cfg.turbo)
        self.ent_proxy.delete(0, "end"); self.ent_proxy.insert(0, self.cfg.proxy)
        self.theme_var.set(self.cfg.theme)
        messagebox.showinfo("Đã tải", "Khôi phục cấu hình từ file.")

    def _sync_cfg_from_ui(self):
        dm = int(self.ent_dmin.get().strip())
        dx = int(self.ent_dmax.get().strip())
        if dm <= 0 or dx < dm:
            raise ValueError("Delay max phải ≥ delay min và > 0")

        cdmin = int(self.ent_cdmin.get().strip())
        cdmax = int(self.ent_cdmax.get().strip())
        if cdmin <= 0 or cdmax < cdmin:
            raise ValueError("Cooldown max phải ≥ cooldown min và > 0")

        burst = int(self.ent_burst.get().strip())
        if burst <= 0:
            raise ValueError("Burst limit phải > 0")

        self.cfg.cookie_ttc = self.ent_cookie.get().strip()
        self.cfg.token_fb = self.ent_token.get().strip()
        self.cfg.delay_min = dm
        self.cfg.delay_max = dx
        self.cfg.cooldown_min = cdmin
        self.cfg.cooldown_max = cdmax
        self.cfg.burst_limit = burst
        self.cfg.proxy = self.ent_proxy.get().strip()
        self.cfg.turbo = bool(self.var_turbo.get())
        self.cfg.theme = self.theme_var.get()

    def _open_log(self):
        try:
            if not os.path.exists(LOG_FILE):
                with open(LOG_FILE, "w", encoding="utf-8") as f:
                    f.write("")
            if sys.platform.startswith("win"):
                os.startfile(LOG_FILE)
            elif sys.platform.startswith("darwin"):
                os.system(f"open '{LOG_FILE}'")
            else:
                os.system(f"xdg-open '{LOG_FILE}'")
        except Exception as e:
            messagebox.showerror("Lỗi", f"Không mở được log: {e}")

# ==========================
# Entry
# ==========================

def main():
    try:
        os.system('cls' if os.name == 'nt' else 'clear')
    except Exception:
        pass
    app = App()
    app.mainloop()

if __name__ == "__main__":
    main()


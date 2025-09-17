import subprocess
import time
import os
import threading
import tkinter as tk
from tkinter import messagebox, ttk, filedialog
from PIL import Image, ImageTk
from pathlib import Path
import sys
import json
from download_logic import handle_url

# --- Settings Management ---
SETTINGS_FILE = "settings.json"

def get_app_support_dir():
    """Returns the path to the app's Application Support directory, creating it if needed."""
    app_name = "YouTubeDownloader"
    # Path is ~/Library/Application Support/AppName on macOS
    app_dir = Path.home() / "Library" / "Application Support" / app_name
    app_dir.mkdir(parents=True, exist_ok=True)
    return app_dir

def get_settings_path():
    """Gets the absolute path to the settings.json file in the app support directory."""
    return get_app_support_dir() / SETTINGS_FILE

def load_settings():
    """Loads settings from the JSON file. Returns defaults if file doesn't exist."""
    settings_path = get_settings_path()
    defaults = {
        "browser": "chrome", 
        "interval_seconds": 600, 
        "max_resolution": "2160",
        "video_format": "mp4",
        "audio_format": "m4a",
        "playlist_as": "audio"
    }
    try:
        if settings_path.exists():
            with open(settings_path, 'r', encoding='utf-8') as f:
                settings = json.load(f)
                # Ensure all keys are present
                for key, value in defaults.items():
                    if key not in settings:
                        settings[key] = value
                return settings
        else:
            save_settings(defaults)
            return defaults
    except (json.JSONDecodeError, IOError):
        save_settings(defaults)
        return defaults

def save_settings(settings):
    """Saves the settings dictionary to the JSON file."""
    settings_path = get_settings_path()
    with open(settings_path, 'w', encoding='utf-8') as f:
        json.dump(settings, f, indent=4)

# --- Core Functions ---
def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

def get_ytdlp_version():
    """Checks if yt-dlp is installed."""
    try:
        process = subprocess.Popen(["yt-dlp", "--version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        stdout, _ = process.communicate()
        return f"yt-dlp: {stdout.strip()}"
    except FileNotFoundError:
        return "yt-dlp 未安装"
    except Exception:
        return ""

def update_ytdlp_status_async(label_widget):
    """Checks yt-dlp version in a separate thread to not block the GUI."""
    def check_version_thread():
        version_str = get_ytdlp_version()
        if label_widget.winfo_exists():
            label_widget.winfo_toplevel().after(0, lambda: label_widget.config(text=version_str))
    thread = threading.Thread(target=check_version_thread, daemon=True)
    thread.start()

def run_gui():
    """Sets up and runs the main Tkinter GUI."""
    cancel_event = threading.Event()

    try:
        vendor_dir = resource_path('vendor')
        if os.path.exists(vendor_dir):
            os.environ['PATH'] = vendor_dir + os.pathsep + os.environ['PATH']
    except Exception as e:
        print(f"Failed to set up embedded vendor path: {e}")

    root = tk.Tk()
    root.withdraw()
    root.title("Universal Downloader")

    style = ttk.Style()
    style.theme_use('clam')

    top_frame = tk.Frame(root)
    top_frame.pack(fill="both", expand=True, padx=10, pady=10)
    middle_frame = tk.Frame(root)
    middle_frame.pack(fill="both", expand=True, padx=10)
    bottom_frame = tk.Frame(root)
    bottom_frame.pack(side="bottom", fill="x", padx=10, pady=10)

    try:
        def add_rounded_corners(im, radius):
            from PIL import ImageDraw
            circle = Image.new('L', (radius * 2, radius * 2), 0)
            draw = ImageDraw.Draw(circle)
            draw.ellipse((0, 0, radius * 2, radius * 2), fill=255)
            alpha = Image.new('L', im.size, 255)
            w, h = im.size
            alpha.paste(circle.crop((0, 0, radius, radius)), (0, 0))
            alpha.paste(circle.crop((radius, 0, radius * 2, radius)), (w - radius, 0))
            alpha.paste(circle.crop((0, radius, radius, radius * 2)), (0, h - radius))
            alpha.paste(circle.crop((radius, radius, radius * 2, radius * 2)), (w - radius, h - radius))
            im.putalpha(alpha)
            return im

        image = Image.open(resource_path("logo/logo.png")).convert("RGBA")
        image = image.resize((80, 80), Image.Resampling.LANCZOS)
        image = add_rounded_corners(image, radius=15)
        logo_img = ImageTk.PhotoImage(image)
        logo_label = tk.Label(top_frame, image=logo_img)
        logo_label.image = logo_img
        logo_label.pack(side="left", padx=(0, 10))
    except Exception as e:
        print(f"⚠️ 加载 logo 失败: {e}")

    controls_frame = tk.Frame(top_frame)
    controls_frame.pack(side="left", fill="x", expand=True)

    tk.Label(controls_frame, text="URL (每行一个):").pack(anchor="w")
    url_input_frame = tk.Frame(controls_frame, bd=1, relief="sunken")
    url_input_frame.pack(fill="both", expand=True, pady=(2, 5))
    url_input = tk.Text(url_input_frame, height=6, wrap='word', relief="flat", borderwidth=0)
    url_input.pack(side="left", fill="both", expand=True)

    dir_frame = tk.Frame(controls_frame)
    dir_frame.pack(fill=tk.X, expand=True, pady=5)
    tk.Label(dir_frame, text="下载根目录:").pack(side=tk.LEFT)
    dir_entry = tk.Entry(dir_frame)
    dir_entry.insert(0, str(Path.home() / "Downloads"))
    dir_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
    browse_btn = ttk.Button(dir_frame, text="选择", command=lambda: select_directory())
    browse_btn.pack(side=tk.LEFT)

    log_label = tk.Label(middle_frame, text="日志:")
    log_label.pack(anchor="w")
    text_area_frame = tk.Frame(middle_frame, bd=1, relief="sunken")
    text_area_frame.pack(pady=2, fill="both", expand=True)
    text_area = tk.Text(text_area_frame, wrap='word', relief="flat", borderwidth=0)
    text_area.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

    def log_callback(msg):
        if text_area.winfo_exists():
            text_area.insert(tk.END, msg)
            text_area.see(tk.END)

    def progress_callback(percentage):
        if progress_bar.winfo_exists():
            progress_bar['value'] = percentage
            root.update_idletasks()

    status_frame = tk.Frame(bottom_frame)
    status_frame.pack(side="top", fill="x")
    status_frame.columnconfigure(0, weight=1)

    status_var = tk.StringVar()
    status_var.set("准备就绪")
    main_status_label = tk.Label(status_frame, textvariable=status_var, anchor='w')
    main_status_label.grid(row=0, column=0, sticky="ew")

    ytdlp_status_label = tk.Label(status_frame, text="Checking...", anchor='e')
    ytdlp_status_label.grid(row=0, column=1, sticky="e")

    update_ytdlp_status_async(ytdlp_status_label)

    progress_bar = ttk.Progressbar(bottom_frame, length=600)
    progress_bar.pack(side="top", fill=tk.X, pady=2)

    def open_settings_window():
        settings_win = tk.Toplevel(root)
        root.settings_win = settings_win  # Keep a reference
        settings_win.withdraw()
        settings_win.title("设置")
        settings_win.geometry("350x350")  # Increased height
        settings_win.resizable(False, False)
        settings_win.transient(root)

        current_settings = load_settings()

        # --- Resolution Mapping ---
        RESOLUTION_MAP = {
            "480p": "480",
            "720p": "720",
            "1080p": "1080",
            "2.5K (1440p)": "1440",
            "4K (2160p)": "2160"
        }
        # Reverse mapping to find display name from value
        RESOLUTION_MAP_REV = {v: k for k, v in RESOLUTION_MAP.items()}

        main_frame = ttk.Frame(settings_win, padding="15")
        main_frame.pack(expand=True, fill="both")

        # --- Browser --- #
        browser_frame = ttk.Frame(main_frame)
        browser_frame.pack(fill="x", pady=5)
        ttk.Label(browser_frame, text="浏览器:").pack(side="left", padx=(0, 10))
        browser_var = tk.StringVar(value=current_settings.get("browser", "chrome"))
        browser_options = ["none", "chrome", "firefox", "brave", "edge", "opera", "safari", "vivaldi", "chromium"]
        browser_combo = ttk.Combobox(browser_frame, textvariable=browser_var, values=browser_options, state="readonly")
        browser_combo.pack(side="left", fill="x", expand=True)

        # --- Download Interval --- #
        interval_frame = ttk.Frame(main_frame)
        interval_frame.pack(fill="x", pady=5)
        ttk.Label(interval_frame, text="下载间隔 (秒):").pack(side="left", padx=(0, 10))
        interval_var = tk.StringVar(value=str(current_settings.get("interval_seconds", 600)))
        interval_entry = ttk.Entry(interval_frame, textvariable=interval_var)
        interval_entry.pack(side="left", fill="x", expand=True)

        # --- Video Resolution --- #
        resolution_frame = ttk.Frame(main_frame)
        resolution_frame.pack(fill="x", pady=5)
        ttk.Label(resolution_frame, text="最高视频画质:").pack(side="left", padx=(0, 10))
        # Get the display name from the saved value, default to '1080p' if not found
        current_res_display = RESOLUTION_MAP_REV.get(str(current_settings.get("max_resolution", "1080")), "1080p")
        resolution_var = tk.StringVar(value=current_res_display)
        resolution_options = list(RESOLUTION_MAP.keys())
        resolution_combo = ttk.Combobox(resolution_frame, textvariable=resolution_var, values=resolution_options, state="readonly")
        resolution_combo.pack(side="left", fill="x", expand=True)

        # --- Video Format --- #
        video_format_frame = ttk.Frame(main_frame)
        video_format_frame.pack(fill="x", pady=5)
        ttk.Label(video_format_frame, text="视频格式:").pack(side="left", padx=(0, 10))
        video_format_var = tk.StringVar(value=current_settings.get("video_format", "mp4"))
        video_format_options = ["mp4", "mkv", "webm"]
        video_format_combo = ttk.Combobox(video_format_frame, textvariable=video_format_var, values=video_format_options, state="readonly")
        video_format_combo.pack(side="left", fill="x", expand=True)

        # --- Audio Format --- #
        audio_format_frame = ttk.Frame(main_frame)
        audio_format_frame.pack(fill="x", pady=5)
        ttk.Label(audio_format_frame, text="音频格式:").pack(side="left", padx=(0, 10))
        audio_format_var = tk.StringVar(value=current_settings.get("audio_format", "m4a"))
        audio_format_options = ["m4a", "mp3", "wav", "flac", "opus"]
        audio_format_combo = ttk.Combobox(audio_format_frame, textvariable=audio_format_var, values=audio_format_options, state="readonly")
        audio_format_combo.pack(side="left", fill="x", expand=True)


        # --- Save Button --- #
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill="x", pady=(20, 0))
        
        def on_save():
            try:
                interval = int(interval_var.get())
                if interval < 0:
                    messagebox.showerror("错误", "间隔不能为负数。", parent=settings_win)
                    return
                
                # Get the numeric value from the display name
                resolution_value = RESOLUTION_MAP.get(resolution_var.get(), "1080")

                new_settings = {
                    "browser": browser_var.get(),
                    "interval_seconds": interval,
                    "max_resolution": resolution_value,
                    "video_format": video_format_var.get(),
                    "audio_format": audio_format_var.get(),
                }
                save_settings(new_settings)
                settings_win.destroy()
            except ValueError:
                messagebox.showerror("错误", "间隔必须是有效的整数。", parent=settings_win)
            except Exception as e:
                messagebox.showerror("错误", f"无法保存设置: {e}", parent=settings_win)

        save_button = ttk.Button(button_frame, text="保存并关闭", command=on_save)
        save_button.pack()

        settings_win.update_idletasks()
        win_width, win_height = 350, 350
        parent_x, parent_y = root.winfo_x(), root.winfo_y()
        parent_width, parent_height = root.winfo_width(), root.winfo_height()
        x = parent_x + (parent_width // 2) - (win_width // 2)
        y = parent_y + (parent_height // 2) - (win_height // 2)
        settings_win.geometry(f'{win_width}x{win_height}+{x}+{y}')
        settings_win.deiconify()
        settings_win.grab_set()

    btn_frame = tk.Frame(bottom_frame)
    btn_frame.pack(side="top", pady=(5,0))
    start_btn = ttk.Button(btn_frame, text="开始下载", command=lambda: on_start())
    start_btn.pack(side=tk.LEFT, padx=10)
    cancel_btn = ttk.Button(btn_frame, text="取消下载", command=lambda: on_cancel(), state=tk.DISABLED)
    cancel_btn.pack(side=tk.LEFT, padx=10)
    settings_btn = ttk.Button(btn_frame, text="设置", command=open_settings_window)
    settings_btn.pack(side=tk.LEFT, padx=10)

    def download_thread():
        urls = [url for url in url_input.get("1.0", tk.END).strip().splitlines() if url.strip()]
        if not urls:
            messagebox.showwarning("提示", "请输入至少一个有效的 URL")
            if root.winfo_exists():
                start_btn.config(state=tk.NORMAL)
                cancel_btn.config(state=tk.DISABLED)
                settings_btn.config(state=tk.NORMAL)
            return

        download_dir = dir_entry.get()
        if not download_dir or not os.path.isdir(download_dir):
            messagebox.showerror("错误", "请输入有效的下载根目录")
            if root.winfo_exists():
                start_btn.config(state=tk.NORMAL)
                cancel_btn.config(state=tk.DISABLED)
                settings_btn.config(state=tk.NORMAL)
            return

        settings = load_settings()
        interval_time = settings.get("interval_seconds", 600)
        
        total_urls = len(urls)
        for i, url in enumerate(urls):
            if cancel_event.is_set():
                log_callback("❌ 下载已被用户取消！\n")
                status_var.set("下载已取消")
                break

            status_var.set(f"({i + 1}/{total_urls}) 开始: {url[:80]}...")
            log_callback(f"\n--- ({i + 1}/{total_urls}) 处理URL: {url} ---\n")

            success = handle_url(url, settings, download_dir, log_callback, cancel_event, status_var, progress_callback)

            if success:
                status_var.set(f"✅ ({i + 1}/{total_urls}) 完成")
            else:
                if not cancel_event.is_set():
                    status_var.set(f"❌ ({i + 1}/{total_urls}) 失败或取消")

            root.update_idletasks()

            if i < total_urls - 1 and not cancel_event.is_set():
                log_callback(f"\n⏳ 等待 {interval_time} 秒...\n")
                try:
                    for remaining in range(interval_time, 0, -1):
                        if cancel_event.is_set(): break
                        mins, secs = divmod(remaining, 60)
                        status_var.set(f"⏳ 等待 {mins:02d}:{secs:02d}...")
                        root.update_idletasks()
                        time.sleep(1)
                except tk.TclError: break

        if not cancel_event.is_set():
            status_var.set("🎉 全部任务完成！")
            log_callback("\n🎉 全部任务完成！\n")
        
        if root.winfo_exists():
            start_btn.config(state=tk.NORMAL)
            cancel_btn.config(state=tk.DISABLED)
            settings_btn.config(state=tk.NORMAL)

    def on_start():
        start_btn.config(state=tk.DISABLED)
        cancel_btn.config(state=tk.NORMAL)
        settings_btn.config(state=tk.DISABLED)
        cancel_event.clear()
        progress_bar["value"] = 0
        root.update_idletasks() # Ensure bar is visually reset
        text_area.delete("1.0", tk.END)
        thread = threading.Thread(target=download_thread, daemon=True)
        thread.start()

    def on_cancel():
        cancel_event.set()
        cancel_btn.config(state=tk.DISABLED)
        log_callback("⚠️ 用户请求取消下载...\n")

    def select_directory():
        path = filedialog.askdirectory(initialdir=dir_entry.get() or str(Path.home() / "Downloads"))
        if path:
            dir_entry.delete(0, tk.END)
            dir_entry.insert(0, path)
    
    def on_closing():
        if start_btn['state'] == tk.DISABLED and cancel_btn['state'] == tk.NORMAL:
            if messagebox.askokcancel("退出", "下载仍在进行中，确定要退出吗？"):
                cancel_event.set()
                root.destroy()
        else:
            root.destroy()

    w, h = 700, 680
    root.update_idletasks()
    sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
    x, y = (sw // 2) - (w // 2), (sh // 2) - (h // 2)
    root.geometry(f'{w}x{h}+{x}+{y}')
    root.minsize(600, 500)
    root.protocol("WM_DELETE_WINDOW", on_closing)
    root.deiconify()
    root.mainloop()

if __name__ == "__main__":
    run_gui()
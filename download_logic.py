import subprocess
import time
import os
import re
import json
import threading

def load_settings() -> dict:
    """从 settings.json 加载配置"""
    try:
        with open("settings.json", "r", encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        print("⚠️ settings.json 未找到或格式错误，将使用默认设置。")
        return {
            "browser": "chrome", 
            "interval_seconds": 600, 
            "max_resolution": "2160",
            "video_format": "mp4",
            "audio_format": "m4a"
        }

def classify_url(url: str) -> str:
    """判断URL类型"""
    if not url.startswith(('http://', 'https://')):
        return "invalid_string"

    if "spotify.com" in url:
        return "unsupported_spotify"
    elif "music.youtube.com" in url and "list=" in url:
        return "music_playlist"
    elif ("youtube.com" in url or "youtu.be" in url):
        if "list=" in url:
            return "video_playlist"
        else:
            return "video"
    else:
        return "video"


def _execute_command(command: list, log_callback, cancel_event, status_var, progress_callback, is_playlist: bool = False, total_playlist_items: int = 1, cwd=None) -> bool:
    """执行外部命令，流式传输输出、处理进度和取消信号"""
    status_var.set("正在下载...")
    progress_callback(0)

    current_video_number = 0  # 0-indexed initially, becomes 1-indexed upon first match

    try:
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding='utf-8',
            errors='ignore',
            cwd=cwd
        )

        for line in process.stdout:
            if cancel_event.is_set():
                process.terminate()
                log_callback("❌ 下载已取消。\n")
                status_var.set("用户取消")
                progress_callback(0)
                return False

            line = line.strip()
            if not line:
                continue
            
            log_callback(line + '\n')

            if is_playlist:
                # First, check if a new item is starting.
                match_item_number = re.search(r'\[download\] Downloading item (\d+) of (\d+)', line)
                if match_item_number:
                    current_video_number = int(match_item_number.group(1))
                    status_var.set(f"正在下载 {current_video_number}/{total_playlist_items}")
                    # Don't process this line for percentage, just continue.
                    continue

                # If we are in a playlist and know which video we are on, process progress.
                if current_video_number > 0:
                    match_percentage = re.search(r'\[download\]\s+([0-9.]+?)%', line)
                    if match_percentage:
                        percentage = float(match_percentage.group(1))
                        
                        # Progress from videos completed *before* the current one.
                        completed_videos_progress = ((current_video_number - 1) / total_playlist_items) * 100
                        
                        # Progress from the current video's own percentage.
                        current_video_progress_contribution = percentage / total_playlist_items
                        
                        overall_percentage = completed_videos_progress + current_video_progress_contribution
                        progress_callback(overall_percentage)

                    # Handle items that are already downloaded separately.
                    elif "has already been downloaded" in line:
                        # This video is 100% done. Update progress to the end of this video.
                        overall_percentage = (current_video_number / total_playlist_items) * 100
                        progress_callback(overall_percentage)
            else:
                # Single video logic (remains simple)
                match_percentage = re.search(r'\[download\]\s+([0-9.]+?)%', line)
                if match_percentage:
                    percentage = float(match_percentage.group(1))
                    progress_callback(percentage)

        process.wait()
        if process.returncode == 0:
            progress_callback(100)
        return process.returncode == 0

    except FileNotFoundError:
        log_callback(f"❌ 命令未找到: {command[0]}。请确保它已安装并位于系统的PATH中。\n")
        status_var.set(f"错误: {command[0]} 未找到")
        return False
    except Exception as e:
        log_callback(f"⚠️ 执行异常: {e}\n")
        status_var.set(f"错误: {e}")
        return False

def download_video(url: str, settings: dict, base_path: str, log_callback, cancel_event, status_var, progress_callback) -> bool:
    """下载单个视频"""
    log_callback(f"🎥 检测到视频链接: {url}\n")
    max_res = settings.get("max_resolution", "1080")
    video_format = settings.get("video_format", "mp4")
    browser = settings.get("browser", "chrome")

    folder = os.path.join(base_path, "videos")
    os.makedirs(folder, exist_ok=True)

    log_callback(f"⬇️ 将以最高 {max_res}p 的画质下载到 {folder} (格式: {video_format})...\n")

    format_string = f"bestvideo[height<={max_res}]+bestaudio/best[height<={max_res}]"
    command = [
        "yt-dlp",
        "--progress",
        "-f", format_string,
        "--merge-output-format", video_format,
        "-o", os.path.join(folder, "%(title)s.%(ext)s"),
        "--newline",
        url
    ]
    if browser and browser.lower() != 'none':
        command.insert(2, "--cookies-from-browser")
        command.insert(3, browser)

    success = _execute_command(command, log_callback, cancel_event, status_var, progress_callback, is_playlist=False, total_playlist_items=1)
    if success:
        log_callback(f"✅ 视频下载成功: {url}\n")
    else:
        if not cancel_event.is_set():
            log_callback(f"❌ 视频下载失败: {url}\n")
    return success

def download_playlist_audio(url: str, settings: dict, base_path: str, log_callback, cancel_event, status_var, progress_callback) -> bool:
    """下载YouTube等来源的播放列表（音频）"""
    log_callback(f"🎼 检测到音频播放列表链接: {url}\n")

    browser = settings.get("browser", "chrome")
    audio_format = settings.get("audio_format", "m4a")

    # Get total items and title from a single meta_command call
    playlist_title = "Untitled Playlist"
    total_items = 0
    try:
        meta_command = ["yt-dlp", "--dump-single-json", "--flat-playlist", url]
        if browser and browser.lower() != 'none':
            meta_command.extend(["--cookies-from-browser", browser])
        meta_process = subprocess.run(meta_command, capture_output=True, text=True, encoding='utf-8', errors='ignore')
        if meta_process.returncode == 0:
            metadata = json.loads(meta_process.stdout)
            playlist_title = metadata.get('title', 'Untitled Playlist')
            total_items = metadata.get('playlist_count', 0)
        else:
            log_callback(f"⚠️ 无法获取播放列表元数据，进度条可能不准确: {meta_process.stderr}\n")
    except Exception as e:
        log_callback(f"⚠️ 获取播放列表元数据时发生错误: {e}\n")

    sanitized_playlist_title = re.sub(r'[/\\?%*:|"<>\\]', '_', playlist_title)

    folder = os.path.join(base_path, "playlists", sanitized_playlist_title)
    os.makedirs(folder, exist_ok=True)

    if total_items == 0:
        log_callback("⚠️ 播放列表为空或无法获取项目数，将尝试下载但进度条可能不准确。\n")
        total_items = 1 # Prevent division by zero

    log_callback(f"⬇️ 正在使用下载播放列表到: {folder} (共 {total_items} 项, 音频格式: {audio_format})\n")
    command = [
        "yt-dlp",
        "--progress",
        "--extract-audio",
        "--audio-format", audio_format,
        "--audio-quality", "0", # Best quality
        "-o", os.path.join(folder, "%(title)s.%(ext)s"),
        "--newline",
        url
    ]
    if browser and browser.lower() != 'none':
        command.insert(2, "--cookies-from-browser")
        command.insert(3, browser)
    success = _execute_command(command, log_callback, cancel_event, status_var, progress_callback, is_playlist=True, total_playlist_items=total_items)

    if success:
        log_callback(f"✅ 音频播放列表下载成功: {url}\n")
    else:
        if not cancel_event.is_set():
            log_callback(f"❌ 音频播放列表下载失败: {url}\n")
    return success

def download_playlist_video(url: str, settings: dict, base_path: str, log_callback, cancel_event, status_var, progress_callback) -> bool:
    """下载YouTube等来源的播放列表（视频）"""
    log_callback(f"🎥 检测到视频播放列表链接: {url}\n")

    browser = settings.get("browser", "chrome")
    max_res = settings.get("max_resolution", "1080")
    video_format = settings.get("video_format", "mp4")

    # Get total items and title from a single meta_command call
    playlist_title = "Untitled Playlist"
    total_items = 0
    try:
        meta_command = ["yt-dlp", "--dump-single-json", "--flat-playlist", url]
        if browser and browser.lower() != 'none':
            meta_command.extend(["--cookies-from-browser", browser])
        meta_process = subprocess.run(meta_command, capture_output=True, text=True, encoding='utf-8', errors='ignore')
        if meta_process.returncode == 0:
            metadata = json.loads(meta_process.stdout)
            playlist_title = metadata.get('title', 'Untitled Playlist')
            total_items = metadata.get('playlist_count', 0)
        else:
            log_callback(f"⚠️ 无法获取播放列表元数据，进度条可能不准确: {meta_process.stderr}\n")
    except Exception as e:
        log_callback(f"⚠️ 获取播放列表元数据时发生错误: {e}\n")

    sanitized_playlist_title = re.sub(r'[/\\?%*:|"<>\\]', '_', playlist_title)

    folder = os.path.join(base_path, "playlists", sanitized_playlist_title)
    os.makedirs(folder, exist_ok=True)

    if total_items == 0:
        log_callback("⚠️ 播放列表为空或无法获取项目数，将尝试下载但进度条可能不准确。\n")
        total_items = 1 # Prevent division by zero

    log_callback(f"⬇️ 正在使用下载播放列表到: {folder} (共 {total_items} 项, 视频格式: {video_format})\n")
    
    format_string = f"bestvideo[height<={max_res}]+bestaudio/best[height<={max_res}]"
    command = [
        "yt-dlp",
        "--progress",
        "-f", format_string,
        "--merge-output-format", video_format,
        "-o", os.path.join(folder, "% (title)s.%(ext)s"),
        "--newline",
        url
    ]
    if browser and browser.lower() != 'none':
        command.insert(2, "--cookies-from-browser")
        command.insert(3, browser)
    success = _execute_command(command, log_callback, cancel_event, status_var, progress_callback, is_playlist=True, total_playlist_items=total_items)

    if success:
        log_callback(f"✅ 视频播放列表下载成功: {url}\n")
    else:
        if not cancel_event.is_set():
            log_callback(f"❌ 视频播放列表下载失败: {url}\n")
    return success

def handle_url(url: str, settings: dict, base_path: str, log_callback, cancel_event, status_var, progress_callback) -> bool:
    """根据URL类型调用相应的下载函数"""
    url_type = classify_url(url)

    if url_type == "video":
        return download_video(url, settings, base_path, log_callback, cancel_event, status_var, progress_callback)
    elif url_type == "music_playlist":
        return download_playlist_audio(url, settings, base_path, log_callback, cancel_event, status_var, progress_callback)
    elif url_type == "video_playlist":
        return download_playlist_video(url, settings, base_path, log_callback, cancel_event, status_var, progress_callback)
    elif url_type == "unsupported_spotify":
        log_callback(f"⚠️ 检测到 Spotify 链接，已跳过: {url}\n")
        status_var.set("不支持Spotify链接")
        return False
    elif url_type == "invalid_string":
        log_callback(f"❌ 无效输入，不是一个合法的URL: {url}\n")
        status_var.set("无效输入")
        return False
    else:
        log_callback(f"❓ 未知URL类型 {url_type}，跳过: {url}\n")
        return False

if __name__ == "__main__":
    class CLIDummy:
        def set(self, value):
            print(f"STATUS: {value}")

    cli_settings = load_settings()
    cli_urls = [
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "https://music.youtube.com/playlist?list=OLAK5uy_kYQ6Lvq-WTFcqHCh0z2EAuMQLmm6TkJe4", # Example music playlist
        "https://www.youtube.com/playlist?list=PL-osiE80TeTsqhIuOqKhwlXsIBj1vCiiP", # Example video playlist
        "this is not a url", # Example of invalid string
    ]

    cli_cancel_event = threading.Event()
    cli_log_callback = lambda msg: print(msg, end='')
    cli_progress_callback = lambda p: print(f"PROGRESS: {p}%")
    cli_base_path = "downloads_cli"

    print(f"CLI模式：文件将下载到 ./{cli_base_path} 文件夹")

    for i, url in enumerate(cli_urls):
        print(f"\n--- 处理URL {i+1}/{len(cli_urls)}: {url} ---")
        success = handle_url(url, cli_settings, cli_base_path, cli_log_callback, cli_cancel_event, CLIDummy(), cli_progress_callback)
        if not success:
            print(f"⚠️ 处理失败或跳过: {url}")

        if i < len(cli_urls) - 1:
            sleep_time = cli_settings.get("interval_seconds", 5)
            print(f"⏳ 等待 {sleep_time} 秒后继续...")
            time.sleep(sleep_time)
    
    print("\n🎉 所有任务完成。")
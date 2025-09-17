# Universal Downloader

这是一个由 AI 创建的基于 Python、Tkinter 和 yt-dlp 构建的简单图形界面下载工具，用于从 YouTube 等网站下载视频和音频。

## ✨ 功能

- **下载单个视频或播放列表**: 支持输入多个URL进行批量下载。
- **智能播放列表检测**: 自动区分 `music.youtube.com` 链接并仅提取音频，其他播放列表则下载为视频。
- **丰富的自定义设置**:
  - **视频画质**: 可从 480p 至 4K (2160p) 中选择。
  - **视频格式**: 支持 mp4, mkv, webm。
  - **音频格式**: 支持 m4a, mp3, wav, flac, opus。
  - **浏览器 Cookie**: 可利用浏览器登录信息下载会员专属或需要登录才能访问的内容。
  - **下载间隔**: 可自定义多个任务之间的等待时间。
- **友好的用户界面**: 提供下载进度条和实时日志输出。

## 🚀 开发与运行

如果你想从源码运行或进行二次开发，请遵循以下步骤：

1. **克隆仓库** (或使用当前项目文件夹)

2. **创建并激活 Python 虚拟环境**:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

3. **安装依赖**
   ```bash
   pip instalL -r requirements.txt
   ```

4. **运行程序**:
   ```bash
   python download_gui.py
   ```

## 📦 打包应用

本项目使用 PyInstaller 进行打包。`YouTubeDownloader.spec` 文件已配置好所有打包选项。

1. **确保 PyInstaller 已安装**:
   ```bash
   pip install pyinstaller
   ```

2. **运行打包命令**:
   ```bash
   python -m PyInstaller YouTubeDownloader.spec --noconfirm
   ```

打包完成后，你可以在 `dist` 目录下找到 `YouTubeDownloader.app`。


## 授权许可

不可商用，仅供学习使用。

**FOR EDUCATIONAL PURPOSE ONLY.**
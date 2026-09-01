import os
import time
import yt_dlp
from yt_dlp.utils import DownloadCancelled


def _try_rename_temp(output_dir: str, format_type: str, downloaded_files: list) -> bool:
    """
    嘗試找到 .temp.mp4 / .temp.m4a 並改名為正式檔案。
    先用獨佔模式開啟確認檔案已釋放，成功改名後回傳 True。
    """
    ext = "mp3" if format_type == "audio" else "mp4"
    for f in os.listdir(output_dir):
        if f.endswith('.temp.mp4') or f.endswith('.temp.m4a'):
            temp_path = os.path.join(output_dir, f)
            # 驗證檔案是否已被系統釋放
            try:
                with open(temp_path, 'a+b'):
                    pass
            except OSError:
                return False  # 仍在鎖定中

            base = f.replace('.temp.mp4', '').replace('.temp.m4a', '')
            final_path = os.path.join(output_dir, f"{base}.{ext}")
            try:
                os.rename(temp_path, final_path)
                if final_path not in downloaded_files:
                    downloaded_files.append(final_path)
                return True
            except OSError:
                return False
    return False


def download_media(url: str, output_dir: str, format_type: str = "audio",
                   status_callback=None, progress_callback=None, stop_event=None):
    """
    使用 yt-dlp 下載 YouTube 影片或播放清單。
    format_type     : 'audio' (mp3) 或 'video' (mp4)
    status_callback : fn(str) — 傳送狀態文字給 UI 顯示
    progress_callback: fn(float) — 傳送 0.0~100.0 進度給 UI 更新進度條
    stop_event      : threading.Event — 背景執行緒下載中途若被設定，會在下一次
                       yt-dlp 進度回呼時中斷這支影片的下載(拋出 DownloadCancelled)。
    回傳下載完成的檔案路徑列表。
    """
    if not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)

    ffmpeg_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'bin')
    archive_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'download_archive.txt')

    def _progress_hook(d):
        if stop_event is not None and stop_event.is_set():
            raise DownloadCancelled("使用者已停止")
        if not progress_callback:
            return
        if d.get('status') == 'downloading':
            total = d.get('total_bytes') or d.get('total_bytes_estimate', 0)
            downloaded = d.get('downloaded_bytes', 0)
            if total > 0:
                progress_callback(min((downloaded / total) * 100.0, 99.0))
        elif d.get('status') == 'finished':
            progress_callback(100.0)

    ydl_opts = {
        'ffmpeg_location': ffmpeg_dir,
        'download_archive': archive_file,
        'outtmpl': os.path.join(output_dir, '%(title)s.%(ext)s'),
        'ignoreerrors': False,
        'no_warnings': True,
        'quiet': False,
        'progress_hooks': [_progress_hook],
    }

    if format_type == "audio":
        ydl_opts['format'] = 'bestaudio/best'
        ydl_opts['postprocessors'] = [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }]
    else:
        ydl_opts['format'] = 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best'
        ydl_opts['merge_output_format'] = 'mp4'

    downloaded_files = []
    info = None

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(url, download=True)

        except Exception as e:
            err_str = str(e)
            is_winlock = (
                "WinError 32" in err_str
                or "being used by another process" in err_str
                or "無法存取" in err_str
                or "[WinError" in err_str
            )

            if is_winlock:
                # ── 重試迴圈：10 秒最多 3 次 → 5 分鐘最多 3 次 ──
                long_retries = 0
                renamed_ok = False

                while long_retries < 3 and not renamed_ok:
                    short_retries = 0
                    while short_retries < 3 and not renamed_ok:
                        short_retries += 1
                        msg = f"⚠️ 檔案鎖定中（第 {short_retries}/3 次），等待 10 秒後重試..."
                        if status_callback:
                            status_callback(msg)
                        else:
                            print(msg)
                        time.sleep(10)
                        renamed_ok = _try_rename_temp(output_dir, format_type, downloaded_files)

                    if not renamed_ok:
                        long_retries += 1
                        if long_retries < 3:
                            msg = f"🔴 短暫重試全部失敗，第 {long_retries}/3 次深度等待，暫停 5 分鐘..."
                            if status_callback:
                                status_callback(msg)
                            else:
                                print(msg)
                            time.sleep(300)
                            renamed_ok = _try_rename_temp(output_dir, format_type, downloaded_files)
                        else:
                            # 3 次 5 分鐘都失敗，放棄
                            msg = f"❌ 嚴重錯誤：檔案鎖定無法解除（已等待超過 15 分鐘），此影片已跳過。錯誤：{err_str[:120]}"
                            if status_callback:
                                status_callback(msg)
                            else:
                                print(msg)
                            return []
            else:
                # 非 WinError 32，直接拋出讓 app.py 顯示
                raise

        # 如果透過重試已經拿到檔案，直接返回
        if downloaded_files:
            return list(set(downloaded_files))

        if info is None:
            return []

        # ── 從 yt-dlp info 解析最終檔案路徑 ──
        def get_all_entries(info_dict):
            entries = []
            if not info_dict:
                return entries
            if 'entries' in info_dict:
                for entry in info_dict['entries']:
                    if entry:
                        entries.extend(get_all_entries(entry))
            else:
                entries.append(info_dict)
            return entries

        all_entries = get_all_entries(info)

        for entry in all_entries:
            if not entry.get('title'):
                continue

            safe_title = yt_dlp.utils.sanitize_filename(entry['title'])
            ext = "mp3" if format_type == "audio" else "mp4"
            filepath = os.path.join(output_dir, f"{safe_title}.{ext}")

            if os.path.exists(filepath):
                downloaded_files.append(filepath)
            else:
                # 備用找法：前 15 字比對
                for f in os.listdir(output_dir):
                    if f.endswith(f'.{ext}'):
                        full_f = os.path.join(output_dir, f)
                        compare_len = min(len(safe_title), 15)
                        if compare_len > 0 and safe_title[:compare_len] in f and full_f not in downloaded_files:
                            downloaded_files.append(full_f)
                            break

    return list(set(downloaded_files))


if __name__ == "__main__":
    test_url = "https://www.youtube.com/watch?v=BaW_C-CGtQc"
    print("Testing download...")

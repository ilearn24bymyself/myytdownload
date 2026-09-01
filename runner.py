import os
import threading
import time

from yt_dlp.utils import DownloadCancelled

from downloader import download_media
from transcriber import Transcriber

_transcriber = None
_transcriber_lock = threading.Lock()


def get_transcriber():
    """跨多次 JobRunner 執行重複使用同一顆已載入模型的 Transcriber，避免每次
    開始批次處理都要重新載入一次模型（GPU/CPU 載入都要花不少時間）。"""
    global _transcriber
    with _transcriber_lock:
        if _transcriber is None:
            _transcriber = Transcriber()
        return _transcriber


class JobRunner:
    """背景執行緒跑「下載 → 語音辨識」整批流程，讓畫面上的開始/暫停/停止
    按鈕可以即時生效。

    跟原本「整段流程卡在一次 Streamlit script 執行裡」的寫法不同——一般的
    st.button 點擊要等目前這次執行完全跑完，下一次腳本重新執行時才讀得到，
    沒辦法中途打斷正在跑的迴圈。這裡把實際工作丟到背景執行緒，Streamlit
    主執行緒只負責輪詢這個物件的屬性來畫面，暫停/停止的訊號透過
    threading.Event 傳進背景執行緒，跟迴圈本身解耦。

    暫停/停止的顆粒度：
      - 下載：yt-dlp 下載單一影片時會不斷呼叫進度回呼，這裡在回呼裡檢查
        stop_event，可以在單一影片下載「中途」中斷；暫停則是等目前這個
        網址下載完才生效——yt-dlp 沒有安全的方式可以在網路傳輸中途凍結
        連線，所以暫停選在「兩個網址之間」這個顆粒度。
      - 語音辨識：faster-whisper 是逐個 segment 產生結果，每算完一個
        segment 檢查一次 pause_event/stop_event，可以在單一檔案轉錄「中途」
        暫停或中斷，不用等整個檔案跑完。

    下載階段跟辨識階段的進度各自用獨立欄位記錄（dl_*/tx_*），不共用同一組，
    這樣切到辨識階段之後，畫面上仍然可以顯示「下載階段最終完成的數字」，
    不會被辨識階段的進度覆蓋掉。
    """

    def __init__(self):
        self.pause_event = threading.Event()
        self.pause_event.set()  # set = 執行中，clear = 暫停中
        self.stop_event = threading.Event()
        self._thread = None

        self.status = "idle"  # idle / running / paused / done / stopped / error
        self.error_message = None
        self.results = []  # [(title, txt_path, status, elapsed), ...]

        self.dl_active = False
        self.dl_done = False
        self.dl_current = 0
        self.dl_total = 0
        self.dl_item_title = ""
        self.dl_item_percent = 0.0

        self.tx_active = False
        self.tx_done = False
        self.tx_current = 0
        self.tx_total = 0
        self.tx_item_title = ""
        self.tx_item_percent = 0.0
        self.device = None
        self.compute_type = None

        self.media_dir = None  # 這次實際處理的影音檔所在資料夾(downloads/或uploads/)，跑完後給畫面拿去開資料夾用

    def start(self, urls, uploaded_paths, options):
        if self.status == "running":
            return
        self.pause_event.set()
        self.stop_event.clear()
        self.status = "running"
        self.error_message = None
        self.results = []
        self.dl_active = self.dl_done = False
        self.dl_current = self.dl_total = 0
        self.dl_item_title = ""
        self.dl_item_percent = 0.0
        self.tx_active = self.tx_done = False
        self.tx_current = self.tx_total = 0
        self.tx_item_title = ""
        self.tx_item_percent = 0.0
        self.media_dir = None
        self._thread = threading.Thread(
            target=self._run, args=(urls, uploaded_paths, options), daemon=True
        )
        self._thread.start()

    def pause(self):
        if self.status == "running":
            self.pause_event.clear()
            self.status = "paused"

    def resume(self):
        if self.status == "paused":
            self.pause_event.set()
            self.status = "running"

    def stop(self):
        self.stop_event.set()
        self.pause_event.set()  # 如果正暫停中，先喚醒讓它能看到 stop 旗標

    def _run(self, urls, uploaded_paths, options):
        try:
            all_paths = []

            if urls:
                self.media_dir = options["downloads_dir"]
            elif uploaded_paths:
                self.media_dir = os.path.dirname(uploaded_paths[0])

            if urls:
                self.dl_active = True
                self.dl_total = len(urls)
                for idx, url in enumerate(urls):
                    self.pause_event.wait()
                    if self.stop_event.is_set():
                        self.status = "stopped"
                        return
                    self.dl_current = idx
                    self.dl_item_title = url
                    self.dl_item_percent = 0.0

                    def status_cb(msg):
                        self.dl_item_title = msg

                    def progress_cb(percent):
                        self.dl_item_percent = percent

                    try:
                        files = download_media(
                            url, options["downloads_dir"], options["format_type"],
                            status_callback=status_cb,
                            progress_callback=progress_cb,
                            stop_event=self.stop_event,
                        )
                    except DownloadCancelled:
                        self.status = "stopped"
                        return

                    if self.stop_event.is_set():
                        self.status = "stopped"
                        return
                    all_paths.extend(files)
                    self.dl_current = idx + 1

                self.dl_done = True

            if uploaded_paths:
                all_paths.extend(uploaded_paths)

            if options["skip_transcription"]:
                self.status = "done"
                self.results = [(os.path.basename(p), p, "downloaded", 0.0) for p in all_paths]
                return

            if not all_paths:
                self.status = "done"
                return

            self.tx_active = True
            self.tx_total = len(all_paths)
            transcriber = get_transcriber()
            self.device = transcriber.device
            self.compute_type = transcriber.compute_type

            for idx, audio_path in enumerate(all_paths):
                self.pause_event.wait()
                if self.stop_event.is_set():
                    self.status = "stopped"
                    return

                title = os.path.splitext(os.path.basename(audio_path))[0]
                txt_path = os.path.join(options["transcripts_dir"], f"{title}.txt")
                # SRT 存在跟影音檔同一個資料夾、同檔名，這樣播放器才能自動抓到字幕，
                # 不用手動複製過去。純文字稿(.txt)還是集中放transcripts_dir。
                srt_path = os.path.join(os.path.dirname(audio_path), f"{title}.srt")
                self.tx_current = idx
                self.tx_item_title = title
                self.tx_item_percent = 0.0

                if not os.path.exists(audio_path):
                    self.results.append((title, None, "error", 0.0))
                    self.tx_current = idx + 1
                    continue

                if options["skip_existing"] and os.path.exists(txt_path):
                    self.results.append((title, txt_path, "skipped", 0.0))
                    self.tx_current = idx + 1
                    continue

                def progress_cb(percent):
                    self.tx_item_percent = percent

                start_time = time.time()
                text_result, segments = transcriber.transcribe(
                    audio_path, progress_callback=progress_cb,
                    pause_event=self.pause_event, stop_event=self.stop_event,
                )
                if self.stop_event.is_set():
                    self.status = "stopped"
                    return
                elapsed = time.time() - start_time

                transcriber.save_transcript(text_result, txt_path)
                if options["output_srt"]:
                    transcriber.save_srt(segments, srt_path)
                self.results.append((title, txt_path, "done", elapsed))

                if options["delete_audio"] and audio_path not in uploaded_paths:
                    try:
                        os.remove(audio_path)
                    except Exception:
                        pass

                self.tx_current = idx + 1

            self.tx_done = True
            self.status = "done"

        except Exception as e:
            self.status = "error"
            self.error_message = str(e)

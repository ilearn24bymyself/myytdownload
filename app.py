import streamlit as st
import os
import datetime

from runner import JobRunner

st.set_page_config(page_title="YouTube Whisperer (Breeze)", page_icon="🎙️", layout="centered")

st.title("🎙️ YouTube Whisperer — Breeze ASR 25")
st.write("將 YouTube 影片批次下載為影片或純音訊，並用 Breeze-ASR-25 自動轉換為純文字稿與 SRT 字幕檔，或直接上傳本機影音檔進行辨識。")

# 路徑設定 (動態當日資料夾)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
today_str = datetime.datetime.now().strftime("%Y%m%d")
TODAY_DIR = os.path.join(BASE_DIR, today_str)

DOWNLOADS_DIR = os.path.join(TODAY_DIR, "downloads")
UPLOADS_DIR = os.path.join(TODAY_DIR, "uploads")
TRANSCRIPTS_DIR = os.path.join(TODAY_DIR, "transcripts")

os.makedirs(DOWNLOADS_DIR, exist_ok=True)
os.makedirs(UPLOADS_DIR, exist_ok=True)
os.makedirs(TRANSCRIPTS_DIR, exist_ok=True)

if "runner" not in st.session_state:
    st.session_state.runner = JobRunner()
runner = st.session_state.runner
busy = runner.status in ("running", "paused")

# ── 輸入模式 ──────────────────────────────────
st.subheader("📋 輸入來源")
input_mode = st.radio(
    "請選擇輸入方式",
    ["單一或播放清單網址", "多個網址（每行一個）", "上傳網址清單 (.txt)", "上傳本機影音檔（略過下載）"],
    horizontal=False,
    disabled=busy,
)

urls_to_process = []
uploaded_media_files = []

if input_mode == "單一或播放清單網址":
    url_input = st.text_input("YouTube 網址", placeholder="https://www.youtube.com/watch?v=... 或播放清單網址", disabled=busy)
    if url_input.strip():
        urls_to_process = [url_input.strip()]

elif input_mode == "多個網址（每行一個）":
    multi_input = st.text_area(
        "每行一個 YouTube 網址",
        placeholder="https://www.youtube.com/watch?v=AAA\nhttps://www.youtube.com/watch?v=BBB",
        height=150,
        disabled=busy,
    )
    if multi_input.strip():
        urls_to_process = [l.strip() for l in multi_input.splitlines() if l.strip().startswith("http")]
        if urls_to_process:
            st.caption(f"已讀取 {len(urls_to_process)} 個網址")

elif input_mode == "上傳網址清單 (.txt)":
    uploaded_file = st.file_uploader("上傳 .txt 檔（每行一個網址）", type=["txt"], disabled=busy)
    if uploaded_file:
        content = uploaded_file.read().decode("utf-8", errors="ignore")
        urls_to_process = [l.strip() for l in content.splitlines() if l.strip().startswith("http")]
        st.success(f"✅ 已讀取 {len(urls_to_process)} 個網址")
        with st.expander("📄 預覽網址清單"):
            for i, u in enumerate(urls_to_process, 1):
                st.text(f"{i}. {u}")

elif input_mode == "上傳本機影音檔（略過下載）":
    st.info("💡 適合情境：YouTube 已下載完成但辨識失敗，或已有本機影音檔案。")
    uploaded_media_files = st.file_uploader(
        "上傳本機影音檔（支援 mp4、mp3、m4a、wav、webm 等）",
        type=["mp4", "mp3", "m4a", "wav", "webm", "ogg"],
        accept_multiple_files=True,
        disabled=busy,
    )
    if uploaded_media_files:
        st.caption(f"已選擇 {len(uploaded_media_files)} 個檔案")

# ── 格式選項 ──────────────────────────────────
st.markdown("---")
st.subheader("⚙️ 處理選項")
dl_format = st.radio("下載格式", ["僅音訊 (MP3)", "高畫質影片 (MP4)"], horizontal=True, disabled=busy)
format_type = "audio" if "MP3" in dl_format else "video"

col1, col2, col3, col4 = st.columns(4)
with col1:
    skip_transcription = st.checkbox("僅下載，不進行語音辨識", value=False, disabled=busy)
with col2:
    delete_audio = st.checkbox("轉換完成後自動刪除暫存檔案", value=False, disabled=busy)
with col3:
    skip_existing = st.checkbox("略過已存在的文字稿", value=True, disabled=busy)
with col4:
    output_srt = st.checkbox("同時輸出 SRT 字幕檔", value=True, disabled=busy)

# ── 開始／暫停／停止 ──────────────────────────────────
st.markdown("---")
is_idle = runner.status in ("idle", "done", "stopped", "error")
is_paused = runner.status == "paused"

ctrl1, ctrl2, ctrl3 = st.columns(3)
with ctrl1:
    if st.button("▶ 開始", type="primary", disabled=not is_idle, use_container_width=True):
        has_input = len(urls_to_process) > 0 or len(uploaded_media_files) > 0
        if not has_input:
            st.error("⚠️ 請先輸入 YouTube 網址或上傳本機影音檔！")
        else:
            saved_uploads = []
            for f in uploaded_media_files:
                save_path = os.path.join(UPLOADS_DIR, f.name)
                with open(save_path, "wb") as out:
                    out.write(f.read())
                saved_uploads.append(save_path)

            options = {
                "downloads_dir": DOWNLOADS_DIR,
                "transcripts_dir": TRANSCRIPTS_DIR,
                "format_type": format_type,
                "skip_transcription": skip_transcription,
                "delete_audio": delete_audio,
                "skip_existing": skip_existing,
                "output_srt": output_srt,
            }
            st.session_state["last_reported_status"] = None
            runner.start(urls_to_process, saved_uploads, options)
            st.rerun()

with ctrl2:
    if st.button("▶ 繼續" if is_paused else "⏸ 暫停", disabled=is_idle, use_container_width=True):
        if is_paused:
            runner.resume()
        else:
            runner.pause()
        st.rerun()

with ctrl3:
    if st.button("⏹ 停止", disabled=is_idle, use_container_width=True):
        runner.stop()
        st.rerun()

if is_paused:
    st.caption("⏸ 已暫停 — 目前這一項處理完後會停在原地，按「繼續」接著跑下一項。")


# ── 進度顯示（每 0.7 秒自動輪詢背景執行緒的狀態，不用整頁重新整理） ──────────
@st.fragment(run_every=0.7 if runner.status in ("running", "paused") else None)
def render_progress():
    r = st.session_state.runner

    # 任務在背景執行緒裡自己跑到終止狀態(done/stopped/error)時，開始/暫停/停止
    # 按鈕跟上面那些輸入欄位都在這個fragment輪詢範圍外，不會自動恢復成可互動——
    # 這裡偵測到「第一次看到這個終止狀態」就強制觸發一次整頁重新整理(scope預設
    # 就是app層級，不是只重跑這個fragment)，讓外層按鈕/輸入欄位的disabled狀態
    # 重新算一次。用session_state記錄「上次已經處理過的狀態」，避免每次輪詢
    # tick都重複觸發整頁重整。
    if r.status in ("done", "stopped", "error") and st.session_state.get("last_reported_status") != r.status:
        st.session_state["last_reported_status"] = r.status
        if r.status == "done":
            try:
                if r.media_dir and os.path.isdir(r.media_dir):
                    os.startfile(r.media_dir)
                if r.tx_active and os.path.isdir(TRANSCRIPTS_DIR):
                    os.startfile(TRANSCRIPTS_DIR)
            except Exception:
                pass
        st.rerun()

    if r.dl_active:
        if r.dl_done:
            label, state, expanded = "✅ 下載完成", "complete", False
        elif r.status == "paused":
            label, state, expanded = "⏸ 下載已暫停", "running", True
        else:
            label, state, expanded = "📥 下載影片中...", "running", True

        with st.status(label, state=state, expanded=expanded):
            total = max(r.dl_total, 1)
            st.caption(f"整體下載進度（{min(r.dl_current, r.dl_total)}/{r.dl_total}）")
            st.progress(min(r.dl_current / total, 1.0))
            if not r.dl_done:
                st.caption(f"目前網址下載進度：{r.dl_item_title}")
                st.progress(min(r.dl_item_percent / 100.0, 1.0))

    if r.tx_active:
        if r.tx_done:
            label, state, expanded = "✅ 語音辨識完成", "complete", False
        elif r.status == "paused":
            label, state, expanded = "⏸ 語音辨識已暫停", "running", True
        else:
            label, state, expanded = "📝 語音辨識中...", "running", True

        with st.status(label, state=state, expanded=expanded):
            if r.device:
                if r.device == "cuda":
                    st.success(f"🟢 GPU 模式  |  compute: `{r.compute_type}`")
                else:
                    st.warning(f"🟡 CPU 模式  |  compute: `{r.compute_type}`")
            total = max(r.tx_total, 1)
            st.caption(f"整體辨識進度（{min(r.tx_current, r.tx_total)}/{r.tx_total}）")
            st.progress(min(r.tx_current / total, 1.0))
            if not r.tx_done:
                st.caption(f"目前檔案辨識進度：{r.tx_item_title}")
                st.progress(min(r.tx_item_percent / 100.0, 1.0))

    if r.status == "stopped":
        st.warning("⏹ 已停止。已完成的檔案維持原樣，尚未處理的項目不會繼續執行。")

    if r.status == "error":
        st.error(f"❌ 發生錯誤：{r.error_message}")

    if r.status == "done":
        st.balloons()
        st.markdown("---")
        st.subheader("📁 處理結果")
        done = sum(1 for _, _, s, _ in r.results if s == "done")
        skip = sum(1 for _, _, s, _ in r.results if s == "skipped")
        err = sum(1 for _, _, s, _ in r.results if s == "error")
        total_time = sum(elapsed for _, _, s, elapsed in r.results if s == "done")
        st.write(f"✅ 轉換：{done}　⏭️ 略過：{skip}　❌ 失敗：{err}　⏱️ 總耗時：{total_time:.1f} 秒")
        st.write(f"📂 文字稿位置：`{today_str}/transcripts`")

        for title, txt_path, status, elapsed in r.results:
            if status == "done" and txt_path:
                with open(txt_path, "r", encoding="utf-8") as f:
                    content = f.read()
                preview = content[:400] + "..." if len(content) > 400 else content
                with st.expander(f"📄 {title}.txt (耗時 {elapsed:.1f}s)"):
                    st.text_area("預覽", value=preview, height=150, disabled=True, key=f"preview_{title}")
            elif status == "skipped":
                st.info(f"⏭️ {title}.txt（已存在，略過）")


render_progress()

st.markdown("---")
st.markdown("<small>Powered by yt-dlp & Breeze-ASR-25（MediaTek Research，本地 GPU，免費）</small>", unsafe_allow_html=True)

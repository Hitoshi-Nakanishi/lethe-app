"""Localized UI strings for Lethe."""

from __future__ import annotations

LANGUAGES = {"ja": "日本語", "en": "English"}
LANGUAGE_CODES = {label: code for code, label in LANGUAGES.items()}
# Button labels (kept as constants because handlers also restore them).
LABEL_RECORD = "●  録音開始"
LABEL_STOP = "■  停止"
LABEL_HQ = "① 高精度で文字起こし"
LABEL_REFINE = "② メモで校正"
LABEL_MINUTES = "③ 議事録を作成"
LABEL_PLAY = "▶  再生"
LABEL_PAUSE = "❚❚  一時停止"

WORKFLOW_HINT = "手順:  録音  →  ① 文字起こし  →  メモに用語を記入  →  ② 校正  →  ③ 議事録"

TOOLTIP_RECORD = "マイク（選択した入力デバイス）の録音を開始／停止します。Space キーでも操作できます。"
TOOLTIP_MIC_CAPTURE = (
    "オフにするとマイク入力を開かず、メモだけを記録できます。音声ファイル、ライブ転写、文字起こしは作成されません。"
)
TOOLTIP_LIVE = (
    "録音中、5 秒ごとに Whisper medium で暫定の文字起こしを表示します。"
    "停止すると自動で「① 高精度で文字起こし」が走り、より正確な結果に置き換わります。"
    "モデル未導入時は自動ダウンロードせず、録音だけを保存できます。"
)
TOOLTIP_NR = "録音音声から定常ノイズ（ファン・空調音など）を除去し、文字起こしの精度を上げます。"
TOOLTIP_OPEN = "既存の音声ファイル(mp3/m4a/wav 等)を開きます。モデル導入済みなら自動で解析し、未導入なら音声だけ読み込みます。"
TOOLTIP_MP3 = "録音した音声を MP3 ファイルとして保存します。"
TOOLTIP_HQ = (
    "録音または開いた音声の全体を選択中の Whisper モデルで文字起こしします。モデル未導入時は確認してからダウンロードします。"
)
TOOLTIP_HQ_MODEL = (
    "「① 高精度で文字起こし」で使うモデル。\n"
    "✓ はダウンロード済み、⬇ は初回利用時にダウンロードが必要です。\n"
    "リストの各モデルは [サイズ / 必要RAM / 品質 / 速度] の目安付きで表示されます。"
)
TOOLTIP_HQ_MODEL_EN = (
    "Whisper model used by '① Transcribe'.\n"
    "✓ already downloaded, ⬇ will download on first use.\n"
    "Each entry shows [disk / RAM / quality / speed] estimates."
)
TOOLTIP_REFINE = (
    "右の「メモ」に書いた固有名詞・専門用語を正しい表記とみなし、"
    "Ollama が文字起こしの誤変換を修正します。先にメモへ用語を入力してください。"
)
TOOLTIP_MINUTES = "文字起こしから Ollama が議事録（要約・論点・アクションアイテム）を Markdown 形式で生成します。"
TOOLTIP_EXPORT_TXT = "文字起こしテキストを .txt / .md ファイルに保存します。"
TOOLTIP_PLAY = "文字起こしの音声を再生します。行頭の [時刻] をクリックすると、その位置から再生できます。"

MIC_HELP = (
    "\n\nマイクが他のアプリで使用中でないか、また\n"
    "システム設定 ＞ プライバシーとセキュリティ ＞ マイク で\n"
    "アクセスが許可されているかご確認ください。"
)

UI_TEXT = {
    "ja": {
        "tagline": "録音・文字起こし・議事録",
        "status_ready": "準備完了",
        "file_menu": "ファイル",
        "open_audio_menu": "音声を開く…",
        "open_session_menu": "セッションを開く…",
        "save_session_menu": "セッションを保存…",
        "export_dataset_menu": "データセットを書き出し…",
        "save_transcript_menu": "文字起こしを保存…",
        "save_mp3_menu": "MP3 を保存…",
        "dark": "Dark",
        "input": "入力",
        "refresh_input": "更新",
        "system_default_input": "システム既定",
        "mic_capture": "マイク音声を取る",
        "noise_reduce": "ノイズ除去",
        "record": LABEL_RECORD,
        "stop": LABEL_STOP,
        "live": "ライブ転写",
        "save_mp3": "MP3 保存",
        "open_audio": "音声を開く",
        "input_level": "入力レベル",
        "mic_off_level": "マイク未使用",
        "analysis": "解析中",
        "transcript": "文字起こし",
        "save": "保存",
        "load": "読込",
        "hq": LABEL_HQ,
        "refine": LABEL_REFINE,
        "minutes": LABEL_MINUTES,
        "workflow": WORKFLOW_HINT,
        "play": LABEL_PLAY,
        "pause": LABEL_PAUSE,
        "click_timestamp": "行頭の [時刻] をクリックでその位置から再生",
        "notes": "メモ",
        "notes_hint": "固有名詞・専門用語・人名などを入力すると、ライブ転写と「② メモで校正」の両方で活用されます。",
        "recording": "録音中",
        "live_tag": "ライブ",
        "noise_tag": "ノイズ除去",
        "mic_off_tag": "マイクなし",
        "record_only_tag": "録音のみ",
        "stopped": "停止 · {seconds:.1f}秒",
        "finalizing": "文字起こしを確定中...",
        "transcribing": "文字起こし中...",
        "transcribe_progress": "文字起こし進捗",
        "transcribe_progress_pct": "文字起こし進捗 · {pct}%",
        "hq_running": "高精度で文字起こし中（{model}）{what}...",
        "hq_download": "モデル {model} をダウンロード中（数分かかります）...",
        "hq_download_cancelled": "ダウンロードを停止しました（{model}）",
        "hq_done": "高精度文字起こし完了（{model}）",
        "hq_empty": "文字起こし結果が空でした",
        "hq_failed": "文字起こしに失敗しました",
        "hq_model_label": "高精度モデル",
        "hq_model_status_ready": "✓ ダウンロード済み",
        "hq_model_status_needs_download": "⬇ 初回ダウンロードあり（約 {size}）",
        "model_install_status": "ライブモデル {live_model}: {live_status}\n高精度モデル {hq_model}: {hq_status}",
        "model_status_installed": "✓ 導入済み",
        "model_status_missing_with_size": "⬇ 未導入（約 {size}）",
        "model_status_missing": "⬇ 未導入",
        "hq_model_combo_entry_cached": "✓ {label}  [{size} / RAM {ram} / 品質 {quality} / 速度 {speed}]",
        "hq_model_combo_entry_uncached": "⬇ {label}  [{size} / RAM {ram} / 品質 {quality} / 速度 {speed}]",
        "cancel_download": "停止",
        "hq_download_confirm_title": "モデルのダウンロード",
        "hq_download_confirm_message": (
            "モデル {model} はまだダウンロードされていません。\n"
            "ダウンロードサイズ: 約 {size}（実行時 RAM 約 {ram}）。\n\n"
            "今ダウンロードを開始しますか？"
        ),
        "refining": "校正中...",
        "refine_running": "Ollama で校正中（{model}）...",
        "refine_done": "校正完了",
        "refine_failed": "校正に失敗しました",
        "minutes_generating": "生成中...",
        "minutes_running": "Ollama で議事録を生成中（{model}）...",
        "minutes_done": "議事録ができました",
        "minutes_failed": "議事録の生成に失敗しました",
        "minutes_window": "議事録",
        "close": "閉じる",
        "save_as_md": ".md として保存",
        "no_recording": "録音がありません。",
        "no_audio": "音声がありません。",
        "audio_ready_model_missing": (
            "音声は保存できます。モデル {model} は未導入のため自動ダウンロードせず、解析は未実行です。"
        ),
        "loaded_audio_label": "読み込み音声",
        "nothing_to_save": "保存する内容がありません。",
        "no_transcript": "文字起こしテキストがありません。",
        "empty_notes": "メモが空です。固有名詞や用語をメモ欄に入力してから実行してください。",
        "saved": "保存しました",
        "save_to": "保存先:\n{path}",
        "session_save_to": "セッションの保存先:\n{path}",
        "dataset_save_to": "データセットの保存先:\n{path}",
        "save_error": "保存できませんでした:\n{error}",
        "load_error": "読み込めませんでした:\n{error}",
        "start_record_error": "録音を開始できませんでした",
        "generic_error": "エラー",
        "save_recording_title": "録音を保存",
        "save_transcript_title": "文字起こしを保存",
        "save_notes_title": "メモを保存",
        "load_notes_title": "メモを読み込み",
        "open_audio_title": "音声ファイルを開く",
        "save_minutes_title": "議事録を保存",
        "save_session_title": "セッションを保存",
        "export_dataset_title": "データセットを書き出し",
        "open_session_title": "セッションを開く",
        "session_loaded": "セッションを読み込みました · {name}",
        "session_open_failed": "セッションを開けませんでした",
        "session_save_failed": "セッションの保存に失敗しました",
        "dataset_save_failed": "データセットの書き出しに失敗しました",
        "settings": "設定",
        "settings_title": "設定",
        "theme_label": "テーマ",
        "language_label": "言語",
        "dark_label": "ダークモード",
    },
    "en": {
        "tagline": "Recorder, transcription, minutes",
        "status_ready": "Ready",
        "file_menu": "File",
        "open_audio_menu": "Open audio...",
        "open_session_menu": "Open session...",
        "save_session_menu": "Save session...",
        "export_dataset_menu": "Export dataset...",
        "save_transcript_menu": "Save transcript...",
        "save_mp3_menu": "Save MP3...",
        "dark": "Dark",
        "input": "Input",
        "refresh_input": "Refresh",
        "system_default_input": "System default",
        "mic_capture": "Capture microphone",
        "noise_reduce": "Noise reduction",
        "record": "●  Record",
        "stop": "■  Stop",
        "live": "Live transcript",
        "save_mp3": "Save MP3",
        "open_audio": "Open audio",
        "input_level": "Input level",
        "mic_off_level": "Mic off",
        "analysis": "Analyzing",
        "transcript": "Transcript",
        "save": "Save",
        "load": "Load",
        "hq": "① Transcribe",
        "refine": "② Correct with notes",
        "minutes": "③ Create minutes",
        "workflow": "Flow:  Record  →  ① Transcribe  →  Add terms to notes  →  ② Correct  →  ③ Minutes",
        "play": "▶  Play",
        "pause": "❚❚  Pause",
        "click_timestamp": "Click a leading [time] to play from that point",
        "notes": "Notes",
        "notes_hint": "Add proper nouns, jargon, names, and terms. Lethe uses them for live transcription and note-based correction.",
        "recording": "Recording",
        "live_tag": "Live",
        "noise_tag": "Noise reduction",
        "mic_off_tag": "Mic off",
        "record_only_tag": "Record only",
        "stopped": "Stopped · {seconds:.1f}s",
        "finalizing": "Finalizing transcript...",
        "transcribing": "Transcribing...",
        "transcribe_progress": "Transcription progress",
        "transcribe_progress_pct": "Transcription progress · {pct}%",
        "hq_running": "High-quality transcription ({model}){what}...",
        "hq_download": "Downloading model {model} (may take several minutes)...",
        "hq_download_cancelled": "Download cancelled ({model})",
        "hq_done": "High-quality transcription complete ({model})",
        "hq_empty": "The transcription result was empty",
        "hq_failed": "Transcription failed",
        "hq_model_label": "HQ model",
        "hq_model_status_ready": "✓ Downloaded",
        "hq_model_status_needs_download": "⬇ First-use download ({size})",
        "model_install_status": "Live model {live_model}: {live_status}\nHQ model {hq_model}: {hq_status}",
        "model_status_installed": "✓ installed",
        "model_status_missing_with_size": "⬇ not installed ({size})",
        "model_status_missing": "⬇ not installed",
        "hq_model_combo_entry_cached": "✓ {label}  [{size} / RAM {ram} / quality {quality} / speed {speed}]",
        "hq_model_combo_entry_uncached": "⬇ {label}  [{size} / RAM {ram} / quality {quality} / speed {speed}]",
        "cancel_download": "Cancel",
        "hq_download_confirm_title": "Download model",
        "hq_download_confirm_message": (
            "Model {model} has not been downloaded yet.\nDownload size: {size} (working RAM {ram}).\n\nStart the download now?"
        ),
        "refining": "Correcting...",
        "refine_running": "Correcting with Ollama ({model})...",
        "refine_done": "Correction complete",
        "refine_failed": "Correction failed",
        "minutes_generating": "Generating...",
        "minutes_running": "Generating minutes with Ollama ({model})...",
        "minutes_done": "Minutes are ready",
        "minutes_failed": "Minutes generation failed",
        "minutes_window": "Minutes",
        "close": "Close",
        "save_as_md": "Save as .md",
        "no_recording": "No recording is available.",
        "no_audio": "No audio is available.",
        "audio_ready_model_missing": (
            "Audio can be saved. Model {model} is not installed, so Lethe did not auto-download or analyze it."
        ),
        "loaded_audio_label": "loaded audio",
        "nothing_to_save": "There is nothing to save.",
        "no_transcript": "There is no transcript text.",
        "empty_notes": "Notes are empty. Add proper nouns or terms before running correction.",
        "saved": "Saved",
        "save_to": "Saved to:\n{path}",
        "session_save_to": "Session saved to:\n{path}",
        "dataset_save_to": "Dataset saved to:\n{path}",
        "save_error": "Could not save:\n{error}",
        "load_error": "Could not load:\n{error}",
        "start_record_error": "Could not start recording",
        "generic_error": "Error",
        "save_recording_title": "Save recording",
        "save_transcript_title": "Save transcript",
        "save_notes_title": "Save notes",
        "load_notes_title": "Load notes",
        "open_audio_title": "Open audio file",
        "save_minutes_title": "Save minutes",
        "save_session_title": "Save session",
        "export_dataset_title": "Export dataset",
        "open_session_title": "Open session",
        "session_loaded": "Loaded session · {name}",
        "session_open_failed": "Could not open session",
        "session_save_failed": "Could not save session",
        "dataset_save_failed": "Could not export dataset",
        "settings": "Settings",
        "settings_title": "Settings",
        "theme_label": "Theme",
        "language_label": "Language",
        "dark_label": "Dark mode",
    },
}


def text_for(language: str, key: str, **kwargs) -> str:
    language = language if language in UI_TEXT else "ja"
    template = UI_TEXT[language].get(key, UI_TEXT["ja"][key])
    return template.format(**kwargs) if kwargs else template

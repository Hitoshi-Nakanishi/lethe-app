# Lethe

デスクトップ向けの録音、ローカル文字起こし、議事録作成ツールです。

Lethe はマイクや任意の入力デバイスから音声を録音し、Whisper でローカル文字起こしを行います。メモに書いた固有名詞や専門用語で文字起こしを校正し、Ollama で Markdown の議事録を生成できます。音声、文字起こし、メモは外部へ送信しません。

このプロジェクトの目的は、現代のデスクトップ上で発生する音声を
ひとつのワークフローで記録し、後から検索・確認できる議事録へ変換する
ことです。

- macOS と Windows の両方で、マイク経由の発話を録音できます。対面会議、
  ナレーション、インタビュー、自分側の通話音声をそのまま記録できます。
- Zoom、YouTube、Web 埋め込みプレイヤーなどの再生音声も、利用可能な
  入力デバイスやループバックデバイスへルーティングすれば録音できます。
- 文字起こしと議事録作成をローカルで完結させ、機密性のある会議音声を
  外部サービスへ送らずに扱えます。

English documentation: [README.md](README.md)

## クイックスタート

```sh
git clone <this repo> lethe-app
cd lethe-app
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -e .
lethe
```

uv を使う場合:

```sh
uv sync --dev
uv run lethe
```

## ドキュメント

- [セットアップガイド](docs/setup.ja.md)
- [使い方ガイド](docs/usage.ja.md)
- [英語版の使い方ガイド](docs/usage.md)

## 主な機能

- Whisper によるローカル文字起こし。録音中のライブプレビューと停止後の高精度パスに対応。
- タイムスタンプ付きの編集可能な文字起こし。タイムスタンプクリックでその位置から再生。
- メモに書いた固有名詞、専門用語、人名を使った校正。
- Ollama による Markdown 議事録生成。
- 音声、文字起こし、メモ、メタデータをまとめたセッション保存。
- 長時間録音でもメモリ使用量が増えにくいディスク保存型録音。
- macOS と Windows の cross-platform 対応。

## 必要なもの

- Python 3.11 以上
- Tk が有効な Python
- 任意: 校正と議事録生成に [Ollama](https://ollama.com)

## テスト

```sh
pytest -q
```

uv を使う場合:

```sh
uv run pytest -q
```

## プロジェクト構成

```text
src/recorder/lethe.py        Tkinter GUI
src/recorder/settings.py     設定保存と一時ファイル掃除
src/recorder/preprocess.py   音声前処理
src/recorder/loopback.py     Windows WASAPI loopback recorder
src/llm/transcribe_stream.py ライブ文字起こし
src/llm/transcribe_final.py  高精度文字起こし
src/llm/refine.py            Ollama による校正
src/llm/summarize.py         Ollama による議事録生成
tests/                       ヘッドレス単体テスト
```

## 名前について

Lethe はギリシャ神話の忘却の川から取った名前です。録音する目的は、会議の内容を頭の中に抱え続けなくて済むようにすることです。

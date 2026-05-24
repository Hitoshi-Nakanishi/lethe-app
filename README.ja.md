# Lethe

デスクトップ向けの録音、ローカル文字起こし、議事録作成ツールです。

Lethe はマイクや任意の入力デバイスから音声を録音し、Whisper でローカル文字起こしを行います。メモに書いた固有名詞や専門用語で文字起こしを校正し、Ollama で Markdown の議事録を生成できます。音声、文字起こし、メモは外部へ送信しません。

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
- macOS と Windows に対応。

## 必要なもの

- Python 3.11 以上
- Tk が有効な Python
- 任意: 校正と議事録生成に [Ollama](https://ollama.com)

## テスト

```sh
pytest -q
```

## プロジェクト構成

```text
src/audios/lethe.py          Tkinter GUI
src/audios/settings.py       設定保存と一時ファイル掃除
src/audios/preprocess.py     音声前処理
src/llm/transcribe_stream.py ライブ文字起こし
src/llm/transcribe_final.py  高精度文字起こし
src/llm/refine.py            Ollama による校正
src/llm/summarize.py         Ollama による議事録生成
tests/                       ヘッドレス単体テスト
```

## 名前について

Lethe はギリシャ神話の忘却の川から取った名前です。録音する目的は、会議の内容を頭の中に抱え続けなくて済むようにすることです。

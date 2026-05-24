# Lethe

デスクトップ向けの録音、ローカル文字起こし、議事録作成ツールです。
macOS と Windows で動作し、音声、文字起こし、メモは外部へ送信しません。

English documentation: [README.md](README.md)

## クイックスタート

[Task](https://taskfile.dev/) と [uv](https://docs.astral.sh/uv/) を入れてから実行します。

```sh
task setup
task run
```

`task setup` は `uv sync --dev` で Python 環境を同期します。
`task run` は Lethe のデスクトップアプリを起動します。

## よく使うタスク

```sh
task test      # pytest を実行
task check     # Ruff lint を実行
task format    # Python ファイルを整形
task default   # format, lint, typecheck, test を実行
task list      # 利用できるタスクを表示
```

## 主な機能

- Whisper によるローカル文字起こし。ライブプレビューと高精度パスに対応。
- タイムスタンプ付き文字起こしとクリック再生。
- メモに書いた固有名詞、専門用語、人名を使った校正。
- Ollama による Markdown 議事録生成。
- 音声、文字起こし、メモ、メタデータをまとめたセッション保存。

## ドキュメント

- [セットアップガイド](docs/setup.ja.md)
- [使い方ガイド](docs/usage.ja.md)
- [英語版の使い方ガイド](docs/usage.md)

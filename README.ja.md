# Lethe

Lethe は、会議、通話、インタビュー、デスクトップ上の音声を文字起こしと
Markdown 議事録に変換するデスクトップアプリです。マイクや利用可能な入力
デバイスから録音し、Whisper でローカル文字起こしを行い、メモに書いた
人名や専門用語で校正し、Ollama で議事録を生成できます。音声、文字起こし、
メモは外部へ送信しません。

English documentation: [README.md](README.md)

## Motivation

会議や通話は、会議室、ヘッドセット、ビデオ会議、ブラウザ再生、ローカル
アプリなど、ばらばらの環境で発生します。Lethe は、その録音から確認までの
流れをローカルで完結させるためのツールです。必要な音声を記録し、検索できる
タイムスタンプ付き文字起こしにし、重要な単語を直し、外部サービスへ音声を
送らずに議事録を作れます。

## クイックスタート

[Task](https://taskfile.dev/) と Python 3.11 以上を入れてから実行します。

```sh
task setup
task run
```

`task setup` は必要に応じて [uv](https://docs.astral.sh/uv/) を用意し、
`uv sync --dev` で Python 環境を同期します。
`task run` は Lethe のデスクトップアプリを起動します。

## 主な機能

- マイク音声や OS から見える入力/ループバック音声を録音。
- メモだけ取りたい場合はマイク音声の取得をオフにできます。
- Whisper によるローカル文字起こし。ライブプレビューと高精度パスに対応。
- タイムスタンプ付き文字起こしとクリック再生。
- メモに書いた固有名詞、専門用語、人名を正しい表記として使った校正。
- Ollama による Markdown 議事録生成。
- 音声、文字起こし、メモ、メタデータをまとめたセッション保存。

## ドキュメント

- [セットアップガイド](docs/setup.ja.md)
- [使い方ガイド](docs/usage.ja.md)
- [英語版の使い方ガイド](docs/usage.md)
- [アーキテクチャとソース構成](docs/architecture.ja.md)

## For Developers

変更を送る前に `task default` を実行します。これは `task format`、
`task check`、`task typecheck`、`task test` をまとめて実行します。

```sh
task format
task check
task typecheck
task test
```

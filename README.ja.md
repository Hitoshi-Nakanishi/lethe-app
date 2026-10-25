# Lethe

[![Tests](https://github.com/Hitoshi-Nakanishi/lethe-app/actions/workflows/tests.yml/badge.svg)](https://github.com/Hitoshi-Nakanishi/lethe-app/actions/workflows/tests.yml)
[![Version](https://img.shields.io/badge/dynamic/toml?url=https%3A%2F%2Fraw.githubusercontent.com%2FHitoshi-Nakanishi%2Flethe-app%2Fmain%2Fpyproject.toml&query=%24.project.version&label=version)](pyproject.toml)
![Python](https://img.shields.io/badge/python-3.14.4-blue)
![Platforms](https://img.shields.io/badge/platform-Windows%20%7C%20macOS-lightgrey)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

Lethe は、会議、通話、インタビュー、デスクトップ上の音声を文字起こしと
Markdown 議事録に変換するデスクトップアプリです。マイクや利用可能な入力
デバイスから録音し、Whisper でローカル文字起こしを行い、メモに書いた
人名や専門用語で校正し、Ollama で議事録を生成できます。音声、文字起こし、
メモは外部へ送信しません。

English documentation: [README.md](README.md)

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/assets/lethe-ja-dark.png">
  <img alt="文字起こしとメモを開いた Lethe の画面" src="docs/assets/lethe-ja-light.png">
</picture>

左側で入力・出力デバイス、録音の設定、モデルを選びます。文字起こしの上に録音と 3 つの処理が並びます。
**① 高精度で文字起こし** は Whisper の高精度パス、**② メモで校正** はメモ欄の表記で人名や用語を直し、
**③ 議事録を作成** は Markdown の議事録を書きます。時刻をクリックすると、その位置から音声を再生します。
下のステータスバーに進み具合と録音時間が出ます。

## Motivation

会議や通話は、会議室、ヘッドセット、ビデオ会議、ブラウザ再生、ローカル
アプリなど、ばらばらの環境で発生します。Lethe は、その録音から確認までの
流れをローカルで完結させるためのツールです。必要な音声を記録し、検索できる
タイムスタンプ付き文字起こしにし、重要な単語を直し、外部サービスへ音声を
送らずに議事録を作れます。

## クイックスタート

[Task](https://taskfile.dev/) と Python 3.14.4 を入れてから実行します。

```sh
task setup
task run
```

`task setup` は必要に応じて [uv](https://docs.astral.sh/uv/) を用意し、
`uv sync --dev` で Python 環境を同期します。
`task run` は Lethe のデスクトップアプリを起動します。

区切りをドラッグすると各領域の幅を変えられます。上部の − / + または Ctrl/Cmd + − / + で文字を拡大・縮小し、
倍率表示をクリックするか Ctrl/Cmd + 0 で標準に戻せます。◐ でライトとダークを切り替え、テーマ（Midnight、Aurora、Ember）と
言語（日本語、英語）は ⚙ から変更できます。

Docker でも開発用のチェックを実行できます。

```sh
docker compose up -d --build app
docker compose exec app task default
```

Docker イメージは Python 3.14.4 と、Lethe が使う Tk、PortAudio、ffmpeg のネイティブライブラリを含み、コンテナのデータを
`.docker-data/` に保存します。Docker からデスクトップ画面と録音を使うには、ホスト側の画面と音声の転送が必要です。詳しくは英語版
[セットアップガイドの Docker の節](docs/setup.md#docker-development-environment) を見てください。

モデルをダウンロードする前に、次を済ませてください。

- `task setup` で Python/uv 環境を用意する。
- LLM モデルをダウンロードする場合は、Ollama をインストールして `ollama serve` を起動する。

設定されているモデルを確認します。

```sh
task model-list
```

Whisper と LLM の 2 種類のモデルをまとめてダウンロードします。

```sh
task download-models
```

`task download-models` は次の両方をダウンロードします。

- 文字起こし用の Whisper モデル: `efwkjn/faster-whisper-ja-760M`
- 校正と議事録生成用の Ollama LLM モデル: `qwen3.5:9b`, `gemma4:12b`

片方だけダウンロードする場合:

```sh
task download-whisper-models
task download-llm-models
```

## 主な機能

- マイク音声に加えて、Windows では PC から出ている音声を既定で録音。
- マイク音声と PC 音声の取得をセッションごとにオン/オフ可能。
- Whisper によるローカル文字起こし。ライブプレビューと高精度パスに対応し、各 Whisper モデルが導入済みかを左側に表示。
- タイムスタンプ付き文字起こしとクリック再生。
- メモに書いた固有名詞、専門用語、人名を正しい表記として使った校正。
- Ollama による Markdown 議事録生成。
- 音声、文字起こし、メモ、メタデータをまとめたセッション保存。
- MP3 音声、文字起こしとメモの Markdown、パスの対応を書いた manifest を 1 つのフォルダーに書き出すデータセット出力。

## ドキュメント

- [セットアップガイド](docs/setup.ja.md)
- [使い方ガイド](docs/usage.ja.md)
- [英語版の使い方ガイド](docs/usage.md)
- [アーキテクチャとソース構成](docs/architecture.ja.md)

## For Developers

変更を送る前に `task default` を実行します。これは整形、lint、
型チェック、テストをまとめて実行します。

```sh
task default
```

[Tests ワークフロー](.github/workflows/tests.yml) は、push と pull request のたびに Windows と macOS で同じチェックを実行し、
パッケージをビルドします。

## 名前について

Lethe はギリシャ神話の忘却の川から取った名前です。録音する目的は、会議の内容を頭の中に抱え続けなくて済むようにすることです。

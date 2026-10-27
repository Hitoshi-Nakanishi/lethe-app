# Lethe

[![Tests](https://github.com/Hitoshi-Nakanishi/lethe-app/actions/workflows/tests.yml/badge.svg)](
https://github.com/Hitoshi-Nakanishi/lethe-app/actions/workflows/tests.yml)
![Python](https://img.shields.io/badge/python-3.14.4-blue)
![Platforms](https://img.shields.io/badge/platform-Windows%20%7C%20macOS-lightgrey)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

**会議の音声から文字起こしと議事録まで、自分の PC で。**

Lethe は、録音、Whisper による文字起こし、メモを使った校正、Ollama による Markdown 議事録の生成を行うデスクトップアプリです。モデルをダウンロードした後の処理はローカルで完結し、音声・文字起こし・メモを外部へ送りません。

English documentation: [README.md](README.md)

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/assets/lethe-ja-dark.png">
  <img alt="文字起こしとメモを開いた Lethe の画面" src="docs/assets/lethe-ja-light.png">
</picture>

文字起こしとメモを並べて確認し、上部のボタンで録音と解析を進めます。時刻をクリックすると、その箇所の音声を聞き直せます。

## 音声から議事録まで

1. **録音する・音声を開く。** マイク音声と、Windows では PC の再生音を録音できます。音声だけ保存して、あとで解析することもできます。
2. **文字起こしを確認する。** タイムスタンプ付きの文章を聞き直しながら編集します。録音中のライブプレビューにも対応しています。
3. **メモで校正する。** 人名や専門用語をメモに書くと、Ollama がその表記を使って誤認識を修正します。
4. **議事録を作成する。** 生成した Markdown を確認・編集して保存します。音声・文字起こし・メモをセッションとしてまとめたり、データセットとして書き出したりできます。

録音と文字起こしだけなら Ollama は不要です。校正と議事録生成には、ローカルの Ollama サービスと LLM が必要です。

## クイックスタート

[Task](https://taskfile.dev/) と Tk 対応の Python 3.14.4 を入れ、チェックアウト先で実行します。

```sh
task setup
task download-whisper-models
task run
```

セットアップは uv で Python 環境を用意し、ダウンロードコマンドは設定済みの音声モデルを取得します。既定のモデルは日本語専用です。言語やモデルの変更は [モデルの設定](docs/setup.ja.md#モデル) を参照してください。

校正と議事録生成も使う場合は、Ollama をインストールして起動した後に実行します。

```sh
task download-llm-models
```

起動したら、左側で音声デバイスを選んで録音を始めます。起動や録音で困った場合は [セットアップガイド](docs/setup.ja.md#トラブルシューティング) を参照してください。

## ドキュメント

- [セットアップ](docs/setup.ja.md): モデル、設定、macOS の Tk 対応、Docker。
- [使い方](docs/usage.ja.md): 録音、聞き直し、セッション、書き出し、表示とショートカット。
- [開発への参加](CONTRIBUTING.md): 開発環境と検査コマンド（英語）。
- [アーキテクチャ](docs/architecture.ja.md): ソース構成と処理の流れ。

[MIT License](LICENSE)。

# Lethe セットアップガイド

English version: [setup.md](setup.md)

## 必要なもの

Tk 対応の Python 3.14.4（`.python-version` の指定）、[Task](https://taskfile.dev/)、音声モデルを保存する数 GB の空き容量が必要です。校正と議事録生成には Ollama も使います。

モデル取得時はインターネットに接続し、その後の処理はローカルで行います。

## インストール

チェックアウト先で実行します。

```sh
task setup
task download-whisper-models
task run
```

`task setup` は必要に応じて uv を用意し、Python 環境を同期します。別のインストール方法は下記を参照してください。

## モデル

既定のモデルは次のとおりです。

| 用途 | モデル |
| --- | --- |
| 文字起こし | `efwkjn/faster-whisper-ja-760M`（日本語専用） |
| 校正・議事録 | Ollama の `qwen3.5:9b`、`gemma4:12b` |

`task setup` の後に使うコマンドです。

| コマンド | 動作 |
| --- | --- |
| `task model-list` | 設定済みモデルを表示 |
| `task download-whisper-models` | 音声モデルを取得 |
| `task download-llm-models` | LLM を取得（Ollama の導入・起動が必要） |
| `task download-models` | 両方を取得（Ollama の起動が必要） |
| `task download-llm-model -- <model>` | 指定した Ollama モデルを取得 |

Ollama はアプリまたは `ollama serve` で起動します。録音と文字起こしだけなら不要です。

別の言語を使う場合は、`default.toml` または非公開の `LETHE_CONFIG` で多言語対応の Whisper モデルを選びます。英語の例です。

```toml
[models]
whisper_live_model = "large-v3-turbo"
whisper_final_model = "large-v3-turbo"
whisper_language = "en"
```

変更後に音声モデルを取得し、アプリでもそのモデルを選びます。画面表示の言語は別の設定です。

## 設定

`default.toml` で保存先、モデル、画面の初期値を指定します。リポジトリ外の TOML を使う場合は `LETHE_CONFIG` にパスを設定してください。`settings.json` に保存済みのユーザー選択がある場合は、
`[defaults]` よりそちらが優先されます。

| セクション | 設定内容 |
| --- | --- |
| `[paths]` | 設定・一時 WAV の保存先と、保存・読み込みダイアログの `datasets_dir` |
| `[models]` | 音声モデルと言語、`ollama_url`、LLM の候補 |
| `[defaults]` | 録音の設定、ライブプレビュー、テーマ、ダークモード、言語、倍率 |
| `[filenames]` | `{timestamp}` と `{meeting_name}` を使う MP3・データセット名のテンプレート |

任意の保存先を空にすると OS の標準動作を使います。推奨ファイル名は保存ダイアログで変更できます。

全項目は [default.toml](../default.toml)、保存されるファイルは [使い方](usage.ja.md#保存先) を参照してください。

## 別のインストール方法

uv がある場合:

```sh
uv sync --dev
uv run lethe
```

または仮想環境を有効にして pip でインストールします。

```sh
python -m pip install -e .
lethe
```

どの方法も同じモデル設定を使います。セットアップ後はモデル取得用の Task コマンドも利用できます。

## Docker

開発用の検査をコンテナで行えます。

```sh
docker compose up -d --build app
docker compose exec app task default
```

イメージには Python 3.14.4、Tk、PortAudio、ffmpeg が含まれます。実行時データは `.docker-data/`、モデルと uv のキャッシュは名前付きボリュームに保存します。

画面表示と録音にはホスト側の転送設定が必要なため、macOS と Windows で対話的に使う場合はホストの Python が簡便です。

Ollama の接続設定を含む詳細は [英語版 Docker ガイド](setup.md#docker-development-environment) を参照してください。

## トラブルシューティング

| 症状 | 確認すること |
| --- | --- |
| `_tkinter` の import エラー | Tcl/Tk 対応の Python を使う |
| Ollama 接続エラー | Ollama を起動し、選んだモデルを取得する |
| 録音が始まらない | マイク権限と他アプリのデバイス使用を確認する |
| 文字起こしが空 | 入力メーターを確認し、ノイズ除去をオフにして試す |

macOS の pyenv Python は、ビルド時に Tcl/Tk が必要です。Tcl/Tk を用意して Python を再ビルドするか、Tk 同梱の Python を使います。次のコマンドで確認できます。

```sh
python -c "import tkinter, _tkinter; print(_tkinter.TK_VERSION)"
```

開発用の検査は [開発への参加](../CONTRIBUTING.md)（英語）を参照してください。

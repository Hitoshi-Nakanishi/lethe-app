# Lethe セットアップガイド

English version: [setup.md](setup.md)

## 必要なもの

- Python 3.14.4 (`.python-version` で指定している標準環境)
- Tk が有効な Python
- Whisper モデルを保存するための数 GB の空き容量
- 任意: 校正と議事録生成に Ollama

## インストール

Task を使う場合:

```sh
git clone <this repo> lethe-app
cd lethe-app
task setup
task run
```

`task setup` は uv が PATH に無い場合も自動で用意します。

List configured models and pre-download the configured set: Whisper `medium`,
`large-v3`; Ollama `llama3.1:8b`, `qwen2.5:7b`, `mistral:7b`.

```sh
task model-list
task download-models
```

uv を使う場合:

```sh
git clone <this repo> lethe-app
cd lethe-app
uv sync --dev
uv run lethe
```

venv と pip を使う場合:

```sh
git clone <this repo> lethe-app
cd lethe-app
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -e .
```

起動:

```sh
lethe
```

## 任意: Ollama

Ollama を入れてサービスを起動し、モデルを取得します。

```sh
ollama serve
task download-llm-model -- llama3.1:8b
```

録音と文字起こしだけなら Ollama は不要です。メモで校正、議事録生成を使う場合に必要です。

## 設定

`default.toml` を編集すると、Lethe の設定保存先、一時 WAV の保存先、保存や読み込みダイアログで共通して使う dataset/output フォルダ、MP3 保存時の推奨ファイル名、アプリに表示する LLM モデル候補を指定できます。リポジトリ外の設定ファイルを使いたい場合は、環境変数 `LETHE_CONFIG` に TOML ファイルのパスを指定します。

UI の初期値も設定できます。これは `settings.json` に値が保存される前だけ使われ、保存済みのユーザー選択がある場合はそちらが優先されます。

```toml
[defaults]
mic_capture = true
noise_reduce = false
live = false
llm_model = "qwen2.5:7b"
theme = "midnight"
dark_mode = true
language = "en"
```

## macOS と Tk

pyenv の Python が Tcl/Tk なしでビルドされている場合、Tkinter の import に失敗します。Homebrew で Tcl/Tk を入れて Tk 対応で Python を再ビルドするか、Tk 同梱の公式 Python を使ってください。

確認:

```sh
python -c "import tkinter, _tkinter; print(_tkinter.TK_VERSION)"
```

## 動作確認

```sh
pytest -q
lethe
```

uv を使う場合:

```sh
uv run pytest -q
uv run lethe
```

## トラブルシューティング

| 症状 | 対処 |
|---|---|
| `_tkinter` import error | Tcl/Tk が有効な Python を使う |
| Ollama 接続エラー | `ollama serve` を起動し、設定したモデルを pull する |
| 録音が始まらない | マイク権限と他アプリのデバイス使用状況を確認する |
| 文字起こしが空 | 入力レベルが動くことを確認し、ノイズ除去を OFF にして試す |

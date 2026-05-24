# Lethe セットアップガイド

English version: [setup.md](setup.md)

## 必要なもの

- Python 3.11 以上
- Tk が有効な Python
- Whisper モデルを保存するための数 GB の空き容量
- 任意: 校正と議事録生成に Ollama

## インストール

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
ollama pull llama3.1:8b
```

録音と文字起こしだけなら Ollama は不要です。メモで校正、議事録生成を使う場合に必要です。

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

## トラブルシューティング

| 症状 | 対処 |
|---|---|
| `_tkinter` import error | Tcl/Tk が有効な Python を使う |
| Ollama 接続エラー | `ollama serve` を起動し、設定したモデルを pull する |
| 録音が始まらない | マイク権限と他アプリのデバイス使用状況を確認する |
| 文字起こしが空 | 入力レベルが動くことを確認し、ノイズ除去を OFF にして試す |

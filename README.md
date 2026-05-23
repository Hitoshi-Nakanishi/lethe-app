# Lethe — 録音・文字起こし・議事録

Lethe はデスクトップ用の音声録音 / 文字起こし / 議事録アプリです。マイク
（または BlackHole 集約デバイス経由の Zoom / YouTube 音声）を録音し、Whisper
で文字起こしし、Ollama で議事録 Markdown に変換します。

すべてローカルで動作し、音声・文字起こしを外部へ送信しません（Ollama 連携を
使う場合もローカルの Ollama に接続します）。

## インストール

```sh
git clone <this repo>
cd lethe-app
python -m venv .venv && source .venv/bin/activate
pip install -e .
```

これで `lethe` コマンドと `python -m audios.lethe` のどちらでも起動できます。

### 追加で必要なもの

- **Tcl/Tk 付き Python**: pyenv ビルドの Python は既定で `_tkinter` を含ま
  ないため、Homebrew の `tcl-tk` を入れて Python を再ビルドします。

  ```sh
  brew install tcl-tk
  TCL_TK_PREFIX="$(brew --prefix tcl-tk)"
  export PKG_CONFIG_PATH="$TCL_TK_PREFIX/lib/pkgconfig:$PKG_CONFIG_PATH"
  export PYTHON_CONFIGURE_OPTS="--with-tcltk-includes='-I${TCL_TK_PREFIX}/include/tcl-tk' --with-tcltk-libs='-L${TCL_TK_PREFIX}/lib -ltcl9.0 -ltcl9tk9.0'"
  export LDFLAGS="-L${TCL_TK_PREFIX}/lib -Wl,-rpath,${TCL_TK_PREFIX}/lib"
  export CPPFLAGS="-I${TCL_TK_PREFIX}/include/tcl-tk"
  pyenv install --force 3.14.4
  ```

- **Ollama**（`② メモで校正` と `③ 議事録を作成` に必要、任意）:

  ```sh
  ollama serve
  ollama pull llama3.1:8b
  ```

  Ollama が起動していなくても録音・文字起こしは動作します。

- 初回の `① 高精度で文字起こし` 実行時に Whisper モデル
  (`kotoba-whisper-v2.0`, 約 1.5 GB) を Hugging Face から自動ダウンロード
  します。

## 使い方（基本フロー）

```
録音  →  ① 高精度で文字起こし  →  メモに用語を記入  →  ② メモで校正  →  ③ 議事録を作成
```

1. **入力デバイス**を選び、必要なら **ノイズ除去** を有効化。
2. **● 録音開始**（または Space キー）。VU メーターでマイク入力を確認。
   - **ライブ転写** を ON にすると、5 秒ごとに簡易プレビューを表示。
3. **■ 停止**。ライブ転写を使っていた場合は自動で `①` が走り、高精度な
   文字起こしに置き換わります。
4. 文字起こしの行頭 `[MM:SS]` をクリックすると、その位置から音声を再生。
   誤りはテキストを直接編集して修正できます。
5. **メモ**欄に固有名詞・専門用語を入力 → **② メモで校正** で Ollama が
   表記を統一。
6. **③ 議事録を作成** で議事録 Markdown を生成。

既存の音声ファイル（mp3 / m4a / wav 等）は **音声を開く**（Cmd/Ctrl+O）から
`①` と同じ高精度パスにかけられます。

## セッションの保存・復元

`ファイル ＞ セッションを保存` で、音声・文字起こし・メモを 1 つの `.zip`
にまとめて保存します。`セッションを開く` で後日そのまま復元できます。

## Zoom / YouTube 音声のキャプチャ（macOS）

マイクではなく「再生中の音声」を録音するには仮想オーディオデバイスが必要です。

1. `brew install blackhole-2ch` で BlackHole をインストール。
2. **Audio MIDI 設定** で「複数出力装置」を作成し、スピーカーと
   BlackHole 2ch を両方チェック。
3. さらに「機器セット」でマイクと BlackHole 2ch を集約。
4. Zoom / ブラウザの音声出力先を「複数出力装置」に設定。
5. Lethe の **入力** で集約した「機器セット」を選択して録音。

Zoom のクラウド録画／ローカル録画が使える場合は、「参加者別に音声ファイル
を記録」設定の方がキャプチャより高品質です。その場合は **音声を開く** で
取り込めます。

## ショートカット

| キー | 動作 |
|---|---|
| Space | 録音開始 / 停止（テキスト欄にフォーカスがない時） |
| Cmd/Ctrl + S | 文字起こしを保存 |
| Cmd/Ctrl + O | 音声ファイルを開く |

## 設定と一時ファイル

- 入力デバイス・ノイズ除去・ライブ転写・ウィンドウサイズは
  `~/.lethe/settings.json` に保存され、次回起動時に復元されます。
- 録音は一時 WAV にストリーム書き出しされます。クラッシュで残った古い
  一時ファイルは起動時に自動で掃除されます。

## 同梱の補助 CLI

歴史的経緯で次の 2 つの CLI も同居しています:

- `python -m audios` — Windows 専用、WASAPI ループバックで「再生中の音声」
  を WAV に保存するヘッドレスツール。`pip install .[loopback]` で
  `soundcard` を追加すると使えます。
- `python -m llm <audio-file>` — 既存の openai-whisper コマンドで音声
  ファイルを文字起こし → Ollama で議事録化するバッチパイプライン。
  別途 `pip install openai-whisper` と `whisper` バイナリが必要。

GUI 単体で使う場合はどちらも不要です。

## テスト

```sh
pytest -q
```

22 件のユニットテストが入っています（音声デバイス・ディスプレイ・ネットワーク
不要）。

## トラブルシューティング

| 症状 | 対処 |
|---|---|
| `_tkinter` が無いと言われて起動しない | 上記の Tcl/Tk 付き Python 再ビルドを実施 |
| `② 校正` / `③ 議事録` で「Ollama に接続できません」 | `ollama serve` を起動し、`ollama pull llama3.1:8b` を実行 |
| 録音を開始できない | マイクが他アプリで使用中でないか、システム設定 ＞ プライバシーとセキュリティ ＞ マイク で許可されているか確認 |
| `①` が長時間「ダウンロード中」のまま | 初回はモデル取得（約 1.5 GB）に数分かかります |

## 起源

`qrxarts` リポジトリの中で育ち、コミット `3a287e1f` 時点で独立リポジトリ
として切り出されました。完全な開発履歴は qrxarts 側の git 履歴に残ります。

# Lethe セットアップガイド

このページは Lethe を初めて使えるようになるまでの手順をまとめたものです。
日常の使い方は [usage.md](usage.md) を参照してください。

## 0. 必要なもの

- **Python 3.11 以上**（3.14 でテスト済み）
- **Tcl/Tk 同梱の Python**: 後述するように pyenv ビルドはここで詰まりがち。
- 約 **4.5 GB のディスク空き**（Whisper モデル用 — large-v3 が ~3 GB、ライブ用 medium が ~1.5 GB）
- **Ollama**: `② メモで校正` と `③ 議事録を作成` を使うなら必要。録音と
  `① 高精度で文字起こし` だけなら不要。

## 1. クローンと venv

```sh
git clone <this repo> lethe-app
cd lethe-app
python -m venv .venv
source .venv/bin/activate                  # Windows: .venv\Scripts\activate
pip install -e .
```

これだけで `lethe` コマンドと `python -m audios.lethe` のどちらでも GUI が
起動できる、はずです。Tcl/Tk が無い Python ビルドだと `_tkinter` 関連の
ImportError が出るので、次のステップを実施してください。

## 2. macOS + pyenv — Tcl/Tk 付きで Python を再ビルド

pyenv が用意する Python は Tcl/Tk を内蔵しないため、Tkinter ベースの
Lethe は起動しません。Homebrew の `tcl-tk` を入れて、その場所を
PYTHON_CONFIGURE_OPTS で指定して Python を再ビルドします。

```sh
brew install tcl-tk

TCL_TK_PREFIX="$(brew --prefix tcl-tk)"
export PKG_CONFIG_PATH="$TCL_TK_PREFIX/lib/pkgconfig:$PKG_CONFIG_PATH"
export PYTHON_CONFIGURE_OPTS="--with-tcltk-includes='-I${TCL_TK_PREFIX}/include/tcl-tk' --with-tcltk-libs='-L${TCL_TK_PREFIX}/lib -ltcl9.0 -ltcl9tk9.0'"
export LDFLAGS="-L${TCL_TK_PREFIX}/lib -Wl,-rpath,${TCL_TK_PREFIX}/lib"
export CPPFLAGS="-I${TCL_TK_PREFIX}/include/tcl-tk"

pyenv install --force 3.14.4               # 5〜15 分かかります
```

ポイント:

- include パスは `include/tcl-tk/`（`include/` ではない）
- Tk ライブラリ名は `libtcl9tk9.0`（標準的な `libtk` ではない）
- 上記オプションは**必ずシングルクォートで**囲む。configure が
  `-L<space>...` を別フラグと誤解するため。

同バージョン (3.14.4 → 3.14.4) で `--force` を付けて上書きすれば、既存
venv の C 拡張パッケージは ABI 互換のまま残ります。検証:

```sh
python -c "import tkinter, _tkinter; print('Tk', _tkinter.TK_VERSION)"
# → Tk 9.0
```

Windows / 公式インストーラ版 Python は最初から Tcl/Tk を同梱しているので
このステップは不要です。

## 3. Ollama（任意 — `②` と `③` 用）

```sh
# macOS
brew install ollama
ollama serve &                # 別ターミナルでも可
ollama pull llama3.1:8b
```

別モデルを使う場合は `src/audios/lethe.py` の `OLLAMA_MODEL` 定数（と
URL の `OLLAMA_URL`）を編集してください。`pull` 済みであればどの GGUF
モデルでも動きます。

Ollama を入れない場合、`② メモで校正` と `③ 議事録を作成` を押すと接続
エラーになりますが、案内ダイアログから対処手順が分かるようになっています。

## 4. BlackHole — Zoom / YouTube 音声をキャプチャ（macOS 任意）

マイク以外、「**再生中の音声**」を録音するには仮想オーディオデバイスが
必要です。

1. `brew install blackhole-2ch`
2. **Audio MIDI 設定** を開く（`open /System/Applications/Utilities/Audio\ MIDI\ Setup.app`）
3. 左下の `+` → **複数出力装置を作成**。
   スピーカーと `BlackHole 2ch` の両方にチェック → 音は引き続きスピーカー
   からも聞こえつつ BlackHole にもコピーされる。
4. 同じく `+` → **機器セットを作成**。
   マイクと `BlackHole 2ch` の両方にチェック → Lethe からはこの集約デバ
   イスが「マイク + システム音声」が混ざった 1 つの入力に見える。
5. Zoom / ブラウザの音声出力先を「複数出力装置」に切り替える。
6. Lethe の **入力** ドロップダウンで集約「機器セット」を選択。

**Zoom のローカル/クラウド録画が使えるなら、Zoom 側の「参加者ごとに音声
ファイルを記録」設定の方が圧倒的に高品質**です。録画 mp3/m4a を後から
**音声を開く**（`Cmd/Ctrl+O`）に投げ込むのが楽です。

## 5. 初回起動 — モデルのダウンロード

`① 高精度で文字起こし` を初めて押すと、Whisper large-v3（約 3 GB）と
（ライブ転写を使う場合は）medium（約 1.5 GB）を Hugging Face から自動
取得します。ステータスバーが「初回モデルをダウンロード中…」になり、
回線速度次第で **10〜30 分**かかります。

モデルは `~/.cache/huggingface/hub/` に置かれます。2 回目以降はキャッ
シュから即ロードされ、転写はすぐに始まります。

## 6. マイク権限（macOS）

初めて録音すると「Python.app がマイクへのアクセスを要求しています」が
出ます。**許可**してください。誤って拒否した場合は:

`システム設定 ＞ プライバシーとセキュリティ ＞ マイク` で **Python**
（または iTerm / Terminal 等、Lethe を起動しているプロセス）を有効化。

## 7. 動作確認

```sh
pytest -q
# → 23 passed
```

GUI 起動:

```sh
lethe                          # コンソールスクリプト
# あるいは
python -m audios.lethe
```

ウィンドウが開いてヘッダーに **Lethe** と表示されれば OK です。

## 8. アンインストール

```sh
deactivate
rm -rf .venv ~/.lethe ~/.cache/huggingface/hub/models--Systran--faster-whisper-large-v3 ~/.cache/huggingface/hub/models--Systran--faster-whisper-medium
```

設定ファイル (`~/.lethe/`) と Whisper モデルキャッシュは別途明示的に
消す必要があります。一時 WAV ファイルは起動時に自動掃除されるので残り
ません。

## トラブルシューティング

| 症状 | 対処 |
|---|---|
| `ModuleNotFoundError: No module named '_tkinter'` | セクション 2 の Tcl/Tk 付き Python 再ビルドを実施 |
| `② 校正` / `③ 議事録` で「Ollama に接続できません」 | `ollama serve` を起動し、`ollama pull llama3.1:8b` を実行 |
| 録音を開始できない | マイクが他アプリで使用中でないか、システム設定で許可されているか確認（セクション 6） |
| `①` がいつまでも「ダウンロード中」 | 初回はモデル取得（large-v3 ~3 GB、medium ~1.5 GB）に十数分かかります |
| 「入力」ドロップダウンに BlackHole が出ない | Audio MIDI 設定で機器セットを作成済みか確認、再表示は `↻` ボタン |
| 録音は動くが転写が空 | 音量が極端に小さい / VAD が無音と判定。`ノイズ除去` を OFF にして試す |

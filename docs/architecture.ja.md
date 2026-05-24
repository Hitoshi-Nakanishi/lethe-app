# Lethe アーキテクチャ

English version: [architecture.md](architecture.md)

## ソース構成

```text
src/recorder/lethe.py        Tkinter GUI
src/recorder/settings.py     設定保存と一時ファイル掃除
src/recorder/preprocess.py   音声前処理
src/recorder/loopback.py     Windows WASAPI loopback recorder
src/llm/transcribe_stream.py ライブ文字起こし
src/llm/transcribe_final.py  高精度文字起こし
src/llm/refine.py            Ollama による校正
src/llm/summarize.py         Ollama による議事録生成
tests/                       ヘッドレス単体テスト
```

## 実行時の構成

デスクトップアプリのワークフローは `recorder.lethe` にまとまっています。GUI が
録音状態、セッション保存/読込、再生、ワーカースレッドとの連携を管理します。
録音中の音声は一時 WAV に書き出すため、長時間録音でもメモリ使用量が増えにくい
構成です。

Whisper 連携は `src/llm` 以下にあります。ライブ文字起こしは短い音声チャンクを
使ってプレビューを出し、高精度文字起こしは音声全体を読み込んでタイムスタンプ
付きセグメントを返します。Ollama による校正と議事録生成は、文字起こしとメモの
テキストを入力として扱います。

from llm.ollama import context_window, generate

MINUTES_PROMPT = """\
あなたは熟練の議事録作成者です。以下は会議や打ち合わせの文字起こしです。
要点を漏らさずに、読みやすい議事録として Markdown 形式で再構成してください。

# 出力フォーマット
## 概要
2〜3行で全体の要約を書く。

## 議題
- 議論された議題を箇条書きで列挙

## 主な論点・決定事項
- 各議題ごとに重要な発言、合意点、決定内容を箇条書きで整理

## アクションアイテム
- [ ] 担当者（不明なら「未定」）: 内容（期限が言及されていれば併記）

## オープン項目 / 次回までの宿題
- 持ち越し論点や未解決の質問

# ルール
- 文字起こしに無い情報は推測せず書かないこと。
- 同じ意味の発言はまとめ、冗長な相槌・フィラーは省略すること。
- 専門用語・固有名詞は文字起こしの表記を尊重すること。

# 文字起こし
"""


def summarize(transcript: str, model: str, ollama_url: str, timeout: float = 600.0) -> str:
    """Send transcript to Ollama and return the minutes-style Markdown."""
    return generate(
        MINUTES_PROMPT + transcript,
        model=model,
        ollama_url=ollama_url,
        num_ctx=context_window(transcript),
        timeout=timeout,
    )

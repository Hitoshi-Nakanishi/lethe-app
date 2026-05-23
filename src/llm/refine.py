"""Post-process a transcript by reconciling it with user-typed notes via Ollama.

The user is expected to type notes (proper nouns, jargon, names) while the
audio plays. Those notes are treated as authoritative: the LLM rewrites the
raw transcript so misheard terms match the spelling in the notes, but the
content and order of the speech are preserved.
"""

import httpx

REFINE_PROMPT = """\
あなたは音声認識結果の校正担当者です。以下は音声の自動文字起こしと、
聞き手が同時に取った手書きメモです。メモに含まれる固有名詞・専門用語・人名は
正しい表記とみなしてください。

ルール:
- メモにある語と一致しそうな箇所（同音異義語・誤変換）はメモの表記に置き換える。
- 文の意味や事実は変えない。要約・追記・削除はしない。
- メモに無い情報を推測で追加しない。
- 行頭の [00:00] 形式のタイムスタンプはそのまま保持し、行の対応も崩さない。
- 出力は校正後の文字起こし本文のみ。前置きや説明・コードブロックは付けない。

# メモ
{notes}

# 文字起こし（校正対象）
{transcript}

# 校正後の文字起こし
"""


def refine_transcript(
    transcript: str,
    notes: str,
    *,
    model: str = "llama3.1:8b",
    ollama_url: str = "http://localhost:11434",
    timeout: float = 300.0,
) -> str:
    """Return the transcript rewritten so terms match the spelling used in notes."""
    if not transcript.strip() or not notes.strip():
        return transcript
    prompt = REFINE_PROMPT.format(notes=notes.strip(), transcript=transcript.strip())
    url = ollama_url.rstrip("/") + "/api/generate"
    payload = {"model": model, "prompt": prompt, "stream": False}
    with httpx.Client(timeout=timeout) as client:
        resp = client.post(url, json=payload)
        resp.raise_for_status()
        data = resp.json()
    return data.get("response", "").strip() or transcript

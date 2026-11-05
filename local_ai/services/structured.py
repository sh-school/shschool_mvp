"""استخراجُ بياناتٍ منظَّمة (JSON Schema) من نصٍّ حرّ — بطاقةُ وثيقةٍ، تصنيفٌ، حقولٌ مخصّصة.

الاستعمالُ العامّ: `extract(text, schema, instructions)` يعيد قاموساً مطابقاً للمخطّط
(LM Studio يفرض المخطّطَ أثناء التوليد)، وتُتحقَّق الحقولُ المطلوبة محلّيّاً بعد الردّ.
`document_card(text)` مخطّطٌ جاهزٌ تستعمله الأتمتة بعد فهرسة كلّ وثيقة (ملخّصٌ، جهةٌ،
تاريخٌ، مستهدَفون، مواعيدُ، إجراءاتٌ) فتظهر في قائمة الوثائق بلا تدخّلٍ يدويّ.
"""

from __future__ import annotations

from typing import Any

from local_ai.client import LMStudioClient, LocalAIError, get_client

#: أقصى نصٍّ يُرسَل للاستخراج — أوّلُ الوثيقة يكفي لبطاقتها، ويحمي سياقَ النموذج (~14K رمز).
MAX_INPUT_CHARS = 12_000

DOCUMENT_CARD_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "title": {"type": "string", "description": "عنوان الوثيقة كما يفهمه القارئ"},
        "kind": {
            "type": "string",
            "enum": ["circular", "policy", "plan", "guide", "form", "report", "other"],
            "description": "تعميم/سياسة/خطّة/دليل/نموذج/تقرير/أخرى",
        },
        "issuer": {"type": "string", "description": "الجهة المُصدِرة إن ذُكرت، وإلّا فارغ"},
        "date": {
            "type": "string",
            "description": "تاريخ الإصدار بصيغة YYYY-MM-DD إن ذُكر، وإلّا فارغ",
        },
        "audience": {
            "type": "array",
            "items": {"type": "string"},
            "description": "الفئات المستهدَفة (معلّمون، أولياء أمور، طلبة الصفّ 12…)",
        },
        "summary": {"type": "string", "description": "ملخّص في جملتين إلى ثلاث بالعربيّة"},
        "deadlines": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"what": {"type": "string"}, "when": {"type": "string"}},
                "required": ["what", "when"],
                "additionalProperties": False,
            },
        },
        "action_items": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "title",
        "kind",
        "issuer",
        "date",
        "audience",
        "summary",
        "deadlines",
        "action_items",
    ],
    "additionalProperties": False,
}

DOCUMENT_CARD_INSTRUCTIONS = (
    "استخرج بطاقةَ الوثيقة التالية. اترك الحقلَ فارغاً إن لم يرد في النصّ، ولا تخترع تواريخَ أو جهات. "
    "لا تُدرج أسماءَ طلبة أو أرقامَ هويّة أو هواتف في أيّ حقل."
)


def extract(
    text: str,
    schema: dict[str, Any],
    *,
    instructions: str,
    schema_name: str = "extraction",
    client: LMStudioClient | None = None,
) -> dict[str, Any]:
    """يعيد قاموساً مطابقاً للمخطّط. يرفع `LocalAIError` إن غاب حقلٌ مطلوب."""
    client = client or get_client()
    messages = [
        {
            "role": "system",
            "content": "أنت مستخرِجُ بياناتٍ دقيق. أجب بكائن JSON واحد فقط يطابق المخطّط.",
        },
        {"role": "user", "content": f"{instructions}\n\n---\n{text[:MAX_INPUT_CHARS]}"},
    ]
    data = client.chat_json(messages, schema, schema_name=schema_name)
    missing = [key for key in schema.get("required", []) if key not in data]
    if missing:
        raise LocalAIError(f"الردُّ ينقصه حقولٌ مطلوبة: {', '.join(missing)}")
    return data


def document_card(text: str, *, client: LMStudioClient | None = None) -> dict[str, Any]:
    """بطاقةُ وثيقة جاهزةٌ (تستعملها أتمتةُ الفهرسة)."""
    return extract(
        text,
        DOCUMENT_CARD_SCHEMA,
        instructions=DOCUMENT_CARD_INSTRUCTIONS,
        schema_name="document_card",
        client=client,
    )


def classify(
    text: str,
    labels: list[str],
    *,
    client: LMStudioClient | None = None,
) -> dict[str, Any]:
    """تصنيفٌ بين تسمياتٍ محدّدة مع تعليلٍ قصير — `{"label": …, "confidence": 0..1, "reason": …}`."""
    schema = {
        "type": "object",
        "properties": {
            "label": {"type": "string", "enum": labels},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            "reason": {"type": "string"},
        },
        "required": ["label", "confidence", "reason"],
        "additionalProperties": False,
    }
    return extract(
        text,
        schema,
        instructions=f"صنّف النصّ التالي إلى واحدةٍ من: {', '.join(labels)}. أعطِ درجةَ ثقةٍ وتعليلاً من جملة.",
        schema_name="classification",
        client=client,
    )

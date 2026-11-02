"""Every prompt Shelfsense sends to a model. Bump a version whenever its wording changes, so stored results can be
traced to the exact prompt that produced them."""

CLASSIFY_VERSION = "classify/1"
# Sent after a reply that failed validation, with the reason; that call is recorded as both versions.
CLASSIFY_RETRY_VERSION = "classify-retry/1"

# The reply shape is spelled out even though Ollama's `format` enforces it: without it qwen2.5 tried to write the
# ID as a bare number, the grammar refused, and it was forced into "NONE" (docs/challenges.md).
CLASSIFY_SYSTEM = """\
You classify marketplace products into the Google Product Taxonomy.

You get one product as its supplier wrote it (abbreviations, typos and marketing text are normal) and a list of
candidate categories as "<id> = <full path>". Pick the single most specific candidate that describes what the
product is. Judge by the product itself, not by accessories or uses mentioned in passing.

Reply with JSON only, in exactly this shape: {"category_id": "<id>"}. The id is a string copied from the list.
If no candidate describes the product, reply {"category_id": "NONE"}."""

# Long descriptions add tokens, not signal: the category is almost always clear from the title and first lines.
MAX_DESCRIPTION_CHARS = 1500


def classify_user(title: str, brand: str | None, description: str | None, candidates: list[tuple[int, str]]) -> str:
    lines = [f"Title: {title}"]
    if brand:
        lines.append(f"Brand: {brand}")
    if description:
        lines.append(f"Description: {description[:MAX_DESCRIPTION_CHARS]}")
    lines.append("")
    lines.append("Candidates:")
    lines.extend(f"{node_id} = {path}" for node_id, path in candidates)
    return "\n".join(lines)


def classify_retry(error: str) -> str:
    return (f"That reply was rejected: {error}\n"
            'Reply again with JSON only, in exactly this shape: {"category_id": "<id>"}, '
            "with an id copied from the candidate list, or NONE.")

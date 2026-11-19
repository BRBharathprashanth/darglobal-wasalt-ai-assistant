import json
import re
import sqlite3
import time
from typing import Any

import requests
from rank_bm25 import BM25Okapi

from app.config import (
    OPENROUTER_API_KEY,
    OPENROUTER_MODEL,
    OPENROUTER_SITE_URL,
    OPENROUTER_SITE_NAME,
    OPENROUTER_MAX_RETRIES,
    OPENROUTER_RETRY_DELAY,
    OPENROUTER_TIMEOUT,
    OPENROUTER_MAX_TOKENS,
    SQLITE_PATH
)


# ==================================================
# 1. TEXT TOKENIZATION
# ==================================================

def tokenize(text: str) -> list[str]:
    """Convert text into lowercase searchable tokens."""

    return re.findall(r"[a-z0-9]+", text.lower())


# ==================================================
# 2. LOCATION-BASED DOCUMENT RETRIEVAL
# ==================================================

def retrieve(
    question: str,
    limit: int = 5
) -> list[dict[str, Any]]:
    """
    Retrieve relevant document chunks using BM25
    and location-based matching.

    Supports:
    - City searches: Riyadh, Jeddah, Dammam.
    - Neighbourhood searches: Al Safa, Al Arid.
    - Property searches using location and specifications.
    - Standard BM25 retrieval for other questions.
    """

    # --------------------------------------------------
    # Load documents from SQLite
    # --------------------------------------------------

    try:

        with sqlite3.connect(SQLITE_PATH) as conn:

            conn.row_factory = sqlite3.Row

            rows = conn.execute(
                """
                SELECT id, source, title, url, content
                FROM chunks
                """
            ).fetchall()

    except sqlite3.Error as exc:

        print(f"Database retrieval error: {exc}")

        return []

    if not rows:
        return []

    # --------------------------------------------------
    # Build BM25 corpus
    # Include title, source and content
    # --------------------------------------------------

    corpus = [

        tokenize(
            f"{row['title']} {row['source']} {row['content']}"
        )

        for row in rows

    ]

    bm25 = BM25Okapi(corpus)

    query_tokens = tokenize(question)

    scores = bm25.get_scores(query_tokens)

    # --------------------------------------------------
    # Identify searchable Wasalt locations
    # --------------------------------------------------

    stopwords = {
        "what",
        "which",
        "where",
        "when",
        "how",
        "are",
        "is",
        "the",
        "in",
        "on",
        "at",
        "for",
        "of",
        "and",
        "or",
        "to",
        "with",
        "wasalt",
        "properties",
        "property",
        "listed",
        "show",
        "find",
        "tell",
        "me",
        "about",
        "available",
        "sale",
        "current",
        "currently",
        "does",
        "do",
        "have",
        "has",
        "there",
        "all",
        "some",
        "any",
        "give",
        "provide",
        "bedroom",
        "bedrooms",
        "bathroom",
        "bathrooms",
        "sqm",
        "square",
        "meter",
        "meters",
        "villa",
        "apartment",
        "building",
        "land",
        "floor",
        "commercial"
    }

    searchable_query_terms = {

        token

        for token in query_tokens

        if len(token) > 2 and token not in stopwords

    }

    # --------------------------------------------------
    # Collect Wasalt documents containing location data
    # --------------------------------------------------

    location_documents = []

    available_location_terms = set()

    for index, row in enumerate(rows):

        if row["source"].lower() != "wasalt":
            continue

        try:

            metadata = json.loads(row["content"])

        except (
            json.JSONDecodeError,
            TypeError
        ):

            continue

        if not isinstance(metadata, dict):
            continue

        location = metadata.get("location", "")

        if not isinstance(location, str) or not location.strip():
            continue

        normalized_location = re.sub(
            r"[^a-z0-9]",
            "",
            location.lower()
        )

        location_tokens = set(
            tokenize(location)
        )

        available_location_terms.update(
            location_tokens
        )

        location_documents.append({

            "index": index,

            "row": row,

            "location": location,

            "normalized_location": normalized_location,

            "location_tokens": location_tokens

        })

    # --------------------------------------------------
    # Match location terms from the question
    #
    # This allows both:
    # "What properties are available in Riyadh?"
    # "What properties are listed in Al Safa, Jeddah?"
    # --------------------------------------------------

    matched_location_terms = (

        searchable_query_terms
        & available_location_terms

    )

    if matched_location_terms:

        location_matches = []

        for document in location_documents:

            location_tokens = document["location_tokens"]

            # Every matched location term must appear
            # in the document location.
            if matched_location_terms.issubset(location_tokens):

                index = document["index"]

                item = dict(document["row"])

                item["score"] = (
                    float(scores[index]) + 100.0
                )

                location_matches.append(item)

        if location_matches:

            location_matches.sort(

                key=lambda item: item["score"],

                reverse=True

            )

            print(
                "Location matching found:",
                len(location_matches),
                "Wasalt documents"
            )

            # Return every matching location record.
            return location_matches

    # --------------------------------------------------
    # STANDARD BM25 FALLBACK
    # --------------------------------------------------

    ranked = sorted(

        enumerate(scores),

        key=lambda item: item[1],

        reverse=True

    )

    results = []

    for index, score in ranked:

        if score <= 0:
            continue

        item = dict(rows[index])

        item["score"] = float(score)

        results.append(item)

        if len(results) >= limit:
            break

    return results


# ==================================================
# 3. GENERATE ANSWER USING OPENROUTER
# ==================================================



# ==================================================
# 3. FORMAT LOCATION-BASED WASALT PROPERTY RESULTS
# ==================================================

def _format_metadata_value(value: Any) -> str:
    """Convert metadata values into readable text without losing details."""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    if value is None or value == "":
        return "Not provided"
    return str(value)


def _format_location_property_results(
    matches: list[dict[str, Any]]
) -> str | None:
    """
    Format complete location-matched Wasalt records locally.
    This avoids model output limits for property searches.
    Returns None when the matches are not all structured Wasalt records.
    """
    records = []

    for item in matches:
        if str(item.get("source", "")).lower() != "wasalt":
            return None

        try:
            metadata = json.loads(item.get("content", ""))
        except (json.JSONDecodeError, TypeError):
            return None

        if not isinstance(metadata, dict) or not metadata.get("location"):
            return None

        records.append((item, metadata))

    if not records:
        return None

    property_specific_keys = {
        "listing_type", "property_type", "property_category",
        "bedrooms", "bathrooms", "price", "price_sar",
        "area", "area_sqm", "size", "plot_area",
        "built_up_area", "property_type_en"
    }

    projects = []
    listings = []

    for item, metadata in records:
        normalized_keys = {str(key).lower() for key in metadata}
        if normalized_keys & property_specific_keys:
            listings.append((item, metadata))
        else:
            projects.append((item, metadata))

    lines = [
        f"## Wasalt property information found ({len(records)} records)",
        "",
        "These results come from the collected knowledge-base records. "
        "They are not a live availability feed.",
        ""
    ]

    def add_section(section_title: str, section_records: list) -> None:
        if not section_records:
            return

        lines.extend([f"### {section_title}", ""])

        for number, (item, metadata) in enumerate(section_records, 1):
            source_number = next(
                (
                    index for index, match in enumerate(matches, 1)
                    if match.get("id") == item.get("id")
                ),
                number
            )

            lines.append(
                f"**{number}. {item.get('title') or 'Untitled record'}** "
                f"[Source {source_number}]"
            )

            for key, value in metadata.items():
                if str(key).lower() in {"url", "source_url"}:
                    continue
                label = str(key).replace("_", " ").strip().title()
                lines.append(f"- {label}: {_format_metadata_value(value)}")

            url = item.get("url", "")
            if url:
                lines.append(f"- Source: {url}")

            lines.append("")

    add_section("Projects", projects)
    add_section("Individual property listings", listings)

    lines.extend([
        "**Important:** A record marked for sale does not confirm that it is "
        "still available. Prices and listing details may change. Please verify "
        "the latest status directly with Wasalt or the relevant seller."
    ])

    return "\n".join(lines)


def answer_question(
    question: str
) -> dict[str, Any]:
    """
    Retrieve relevant information and generate
    an answer using an OpenRouter model.
    """

    # --------------------------------------------------
    # Retrieve relevant documents
    # --------------------------------------------------

    try:

        matches = retrieve(question)

    except Exception as exc:

        print(f"Retrieval error: {exc}")

        return {

            "answer": (
                "Unable to retrieve information "
                "from the knowledge base."
            ),

            "sources": []

        }

    if not matches:

        return {

            "answer": (
                "No relevant information was found "
                "in the knowledge base."
            ),

            "sources": []

        }

    # --------------------------------------------------
    # Prepare context and sources
    # --------------------------------------------------

    context_parts = []

    sources = []

    for index, item in enumerate(matches, 1):

        context_parts.append(

            f"[Source {index}]\n"
            f"Company: {item['source']}\n"
            f"Title: {item['title']}\n"
            f"URL: {item.get('url', '')}\n"
            f"Information:\n{item['content']}"

        )

        sources.append({

            "source_id": index,

            "title": item["title"],

            "url": item.get("url", "")

        })

    context = "\n\n".join(context_parts)

    # Location-matched Wasalt property searches are formatted directly
    # from the retrieved records so every match is included without
    # depending on the free model's output-token limit.
    property_search_terms = {
        "property", "properties", "listing", "listings", "villa",
        "villas", "apartment", "apartments", "land", "lands",
        "project", "projects", "available", "sale", "for"
    }
    question_terms = set(tokenize(question))
    is_property_search = bool(question_terms & property_search_terms)

    if is_property_search:
        direct_answer = _format_location_property_results(matches)
        if direct_answer is not None:
            print(
                "Returning all location-matched Wasalt records "
                "without an OpenRouter request."
            )
            return {
                "answer": direct_answer,
                "sources": sources
            }

    # --------------------------------------------------
    # Check OpenRouter API key
    # --------------------------------------------------

    if not OPENROUTER_API_KEY:

        return {

            "answer": (
                "OpenRouter API key is missing. "
                "Please check your .env file."
            ),

            "sources": sources

        }

    # ==================================================
    # 4. SYSTEM PROMPT
    # ==================================================

    system_prompt = """
You are a professional real estate AI assistant
for DarGlobal and Wasalt.

Your task is to answer questions using only
the retrieved knowledge base context.

GENERAL RULES:

1. Use only the information provided in the retrieved context.

2. Never invent property prices, availability,
   locations, project details or specifications.

3. Clearly distinguish DarGlobal from Wasalt.

4. Include relevant projects and property information.

5. Cite factual claims using the exact source numbers
   provided in the retrieved context.

6. Only cite sources that directly support your claims.

7. If information is unavailable, clearly say so.

8. Prices and property availability may change.

9. Keep answers clear, professional and helpful.

10. Do not make assumptions beyond the supplied context.

PROPERTY SEARCH RULES:

11. For location-specific questions, examine all
    matching property records in the retrieved context.

12. Include every matching property when the user
    asks for properties in a specific location.

13. Do not omit matching properties because they
    have different property types.

14. Do not include properties from unrelated locations.

15. For city-level searches, list the specific
    matching property records available for that city.

16. Do not present general Saudi Arabia property
    categories as specific properties in Riyadh.

17. If no specific property records are found,
    clearly explain that the available context
    does not provide more specific listings.

18. Distinguish project records from individual
    property listings.

19. Include the source URL when available.

PROPERTY AVAILABILITY RULES:

20. Never infer current availability from
    listing_type = sale.

21. A sale listing is not proof that a property
    is currently available.

22. If the user asks whether a property is currently
    available, clearly state that live availability
    cannot be confirmed from historical dataset records.

23. Never claim that a property is available,
    sold, reserved or under offer unless the
    retrieved context explicitly confirms that status.

24. Explain that the user should verify the current
    status directly with Wasalt or the relevant seller.

ANSWER FORMATTING:

25. Use clear headings and numbered lists.

26. For city-level property searches, separate
    project records from individual property listings.

27. Display each property using this format:

    Property or Project Name
    - Location:
    - Property Type:
    - Price:
    - Specifications:
    - Source: Include the supplied URL.

28. Include every matching record returned in the context.

29. Do not create large Markdown tables for long
    property lists. Use compact numbered entries.

30. Mention missing property specifications
    instead of inventing them.

31. Keep the answer concise and avoid repeating
    source information.

32. Clearly explain historical listing limitations
    and do not claim live availability.
DATASET LIMITATIONS:

32. The knowledge base contains collected
    public information and historical listing snapshots.

33. Do not describe the dataset as a live property feed.

34. Do not claim that every property on DarGlobal
    or Wasalt is represented in the knowledge base.
"""

    # ==================================================
    # 5. OPENROUTER REQUEST
    # ==================================================

    payload = {

        "model": OPENROUTER_MODEL,

        "messages": [

            {

                "role": "system",

                "content": system_prompt

            },

            {

                "role": "user",

                "content": (

                    f"Retrieved Context:\n\n"
                    f"{context}\n\n"
                    f"User Question:\n{question}\n\n"
                    "Answer using the retrieved context "
                    "and follow all system instructions."

                )

            }

        ],

        "temperature": 0.2,

        "max_tokens": OPENROUTER_MAX_TOKENS

    }

    headers = {

        "Authorization": (
            f"Bearer {OPENROUTER_API_KEY}"
        ),

        "Content-Type": "application/json",

        "HTTP-Referer": OPENROUTER_SITE_URL,

        "X-Title": OPENROUTER_SITE_NAME

    }

    session = requests.Session()

    # Bypass problematic environment proxy settings.
    session.trust_env = False

    # OPENROUTER_MAX_RETRIES means retries after the first request.
    max_attempts = max(1, OPENROUTER_MAX_RETRIES + 1)
    retryable_status_codes = {429, 500, 502, 503, 504}
    truncation_retry_used = False

    try:
        for attempt in range(max_attempts):
            print(
                f"Sending OpenRouter request "
                f"(attempt {attempt + 1}/{max_attempts})..."
            )

            try:
                response = session.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers=headers,
                    json=payload,
                    timeout=(20, OPENROUTER_TIMEOUT)
                )
            except requests.exceptions.Timeout:
                if attempt < max_attempts - 1:
                    wait_seconds = min(
                        OPENROUTER_RETRY_DELAY * (2 ** attempt), 60
                    )
                    print(
                        f"OpenRouter timed out. Retrying in "
                        f"{wait_seconds:.1f} seconds..."
                    )
                    time.sleep(wait_seconds)
                    continue
                raise

            # Retry rate limits and temporary provider/server errors.
            if response.status_code in retryable_status_codes:
                if attempt < max_attempts - 1:
                    retry_after = response.headers.get("Retry-After", "")
                    try:
                        wait_seconds = float(retry_after)
                    except (TypeError, ValueError):
                        wait_seconds = OPENROUTER_RETRY_DELAY * (2 ** attempt)

                    wait_seconds = min(max(wait_seconds, 1), 60)
                    print(
                        f"OpenRouter returned HTTP {response.status_code}. "
                        f"Retrying in {wait_seconds:.1f} seconds..."
                    )
                    time.sleep(wait_seconds)
                    continue

            response.raise_for_status()
            data = response.json()
            choices = data.get("choices", [])

            if not choices:
                raise ValueError(
                    f"OpenRouter returned no choices: {data}"
                )

            choice = choices[0]
            message = choice.get("message", {})
            answer = message.get("content")
            finish_reason = choice.get("finish_reason")

            # Some providers return content as text blocks.
            if isinstance(answer, list):
                answer = "\n".join(
                    item.get("text", "")
                    for item in answer
                    if isinstance(item, dict)
                )

            if isinstance(answer, str) and answer.strip():
                cleaned_answer = answer.strip()

                # A non-empty answer can still be truncated by the provider.
                if finish_reason == "length":
                    print(
                        "OpenRouter stopped at its output limit; "
                        "the response may be incomplete."
                    )

                    if not truncation_retry_used and attempt < max_attempts - 1:
                        truncation_retry_used = True
                        print("Retrying once because the response was truncated...")
                        time.sleep(min(OPENROUTER_RETRY_DELAY, 10))
                        continue

                    cleaned_answer += (
                        "\n\n*Note: The model reached its response limit, "
                        "so this answer may be incomplete.*"
                    )

                print("OpenRouter response received successfully.")
                return {
                    "answer": cleaned_answer,
                    "sources": sources
                }

            print(
                f"OpenRouter returned an empty answer. "
                f"Finish reason: {finish_reason}"
            )

            if attempt < max_attempts - 1:
                wait_seconds = min(
                    OPENROUTER_RETRY_DELAY * (2 ** attempt), 60
                )
                print(
                    f"Retrying empty response in {wait_seconds:.1f} seconds..."
                )
                time.sleep(wait_seconds)
                continue

        return {
            "answer": (
                "The AI model did not return a usable response after "
                "several attempts. Please try again in a few moments."
            ),
            "sources": sources
        }

    except requests.exceptions.Timeout as exc:
        print(f"OpenRouter timeout error: {exc}")
        return {
            "answer": (
                "The AI model is taking too long to respond. "
                "Please try again."
            ),
            "sources": sources
        }

    except requests.exceptions.HTTPError as exc:
        status_code = (
            exc.response.status_code
            if exc.response is not None
            else "unknown"
        )
        print(f"OpenRouter HTTP error ({status_code}): {exc}")

        if status_code == 429:
            message = (
                "OpenRouter is temporarily rate-limiting requests. "
                "Please wait a short time and try again."
            )
        elif status_code in (401, 403):
            message = (
                "OpenRouter rejected the API key or account permissions. "
                "Check the API key configured in your environment."
            )
        else:
            message = (
                f"OpenRouter returned an HTTP error ({status_code}). "
                "Please try again later."
            )

        return {"answer": message, "sources": sources}

    except requests.exceptions.RequestException as exc:
        print(f"OpenRouter request error: {exc}")
        return {
            "answer": f"OpenRouter request failed: {exc}",
            "sources": sources
        }

    except (KeyError, IndexError, TypeError, ValueError) as exc:
        print(f"OpenRouter response error: {exc}")
        return {
            "answer": (
                "The AI model returned an invalid response. "
                "Please try again."
            ),
            "sources": sources
        }

    finally:
        session.close()
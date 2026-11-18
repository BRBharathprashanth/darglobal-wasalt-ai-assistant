
import json
import re
import sqlite3
from typing import Any

import requests
from rank_bm25 import BM25Okapi

from app.config import (
    OPENROUTER_API_KEY,
    OPENROUTER_MODEL,
    OPENROUTER_SITE_URL,
    OPENROUTER_SITE_NAME,
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

25. Use clear headings and bullet points.

26. Include prices in SAR.

27. Mention missing property specifications
    instead of inventing them.

28. Avoid repeating irrelevant information.

29. Do not cite unrelated sources just to increase
    the number of citations.

30. Use natural spacing and readable formatting.

31. Do not provide fabricated phone numbers,
    contact information or website links.

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

        "max_tokens": 1000

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

    max_attempts = 2

    try:

        for attempt in range(max_attempts):

            print(

                f"Sending OpenRouter request "
                f"(attempt {attempt + 1}/{max_attempts})..."

            )

            response = session.post(

                "https://openrouter.ai/api/v1/chat/completions",

                headers=headers,

                json=payload,

                timeout=(20, 120)

            )

            response.raise_for_status()

            data = response.json()

            choices = data.get("choices", [])

            if not choices:

                raise ValueError(

                    f"OpenRouter returned no choices: {data}"

                )

            message = choices[0].get(

                "message",

                {}

            )

            answer = message.get("content")

            # Handle content returned as text blocks.
            if isinstance(answer, list):

                answer = "\n".join(

                    item.get("text", "")

                    for item in answer

                    if isinstance(item, dict)

                )

            if (

                isinstance(answer, str)

                and answer.strip()

            ):

                print(
                    "OpenRouter response received successfully."
                )

                return {

                    "answer": answer.strip(),

                    "sources": sources

                }

            finish_reason = choices[0].get(
                "finish_reason"
            )

            print(

                f"Empty response on attempt "
                f"{attempt + 1}. "
                f"Finish reason: {finish_reason}"

            )

            # Retry once with an increased token limit.
            if attempt < max_attempts - 1:

                payload["max_tokens"] = 1400

                print(
                    "Retrying with an increased token limit..."
                )

                continue

        return {

            "answer": (

                "The AI model could not generate "
                "a complete response after two attempts. "
                "Please try again."

            ),

            "sources": sources

        }

    # ==================================================
    # 6. ERROR HANDLING
    # ==================================================

    except requests.exceptions.Timeout as exc:

        print(
            f"OpenRouter timeout error: {exc}"
        )

        return {

            "answer": (

                "The AI model is taking too long "
                "to respond. Please try again."

            ),

            "sources": sources

        }

    except requests.exceptions.RequestException as exc:

        print(
            f"OpenRouter request error: {exc}"
        )

        return {

            "answer": (
                f"OpenRouter request failed: {exc}"
            ),

            "sources": sources

        }

    except (

        KeyError,
        IndexError,
        TypeError,
        ValueError

    ) as exc:

        print(
            f"OpenRouter response error: {exc}"
        )

        return {

            "answer": (

                "The AI model returned an invalid response. "
                "Please try again."

            ),

            "sources": sources

        }

    finally:

        session.close()

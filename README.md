# DarGlobal & Wasalt Real Estate AI Assistant

Docker-ready RAG chatbot that collects permitted public website content, indexes it with ChromaDB and Sentence Transformers, and answers questions through OpenRouter.

## Stack
Python, FastAPI, Streamlit, BeautifulSoup, Trafilatura, ChromaDB, Sentence Transformers, OpenRouter and Docker.

## Run locally
1. Install Docker Desktop.
2. Copy `.env.example` to `.env` and set `OPENROUTER_API_KEY`.
3. Run `docker compose up --build`.
4. Open http://localhost:8501 (chat UI) or http://localhost:8000/docs (API).

Default model routing is `openrouter/free`. You can replace it with a currently listed free chat model ID in `.env`. Free model availability and quotas are controlled by OpenRouter and can change.

## Scraping and compliance
The crawler starts at the DarGlobal and Wasalt public home pages, stays on each seed domain, checks `robots.txt`, uses a descriptive user agent and waits between requests. It fails closed if it cannot read the site's robots policy. It does not bypass login, CAPTCHA, paywalls or other restrictions. Respect each site's terms and applicable law. If a site blocks crawling, use an approved sitemap, public downloadable materials, or written permission rather than bypassing controls.

## Data and freshness
Scraped text is saved to `data/scraped_pages.jsonl`; the local vector index is saved under `data/chroma`. Rebuild the index by rerunning `python -m app.ingest`. Property availability, prices and offers may change; confirm them with the official provider.

## Deployment
Deploy this Docker container on a host that supports persistent storage and environment variables. Set `OPENROUTER_API_KEY`, `OPENROUTER_MODEL`, `OPENROUTER_SITE_URL`, and `OPENROUTER_SITE_NAME`. Expose the Streamlit port (8501) publicly and keep the API port (8000) private where possible. Attach persistent storage to `/app/data` so the vector index survives restarts.

## Project layout
- `app/scraper.py`: robots-aware public page crawler
- `app/ingest.py`: text chunking and vector indexing
- `app/rag.py`: retrieval and grounded OpenRouter answer generation
- `app/api.py`: FastAPI chat endpoint
- `app/ui.py`: Streamlit chat interface
- `Dockerfile`, `docker-compose.yml`: container setup

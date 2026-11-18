import time
import urllib.robotparser
from collections import deque
from urllib.parse import urljoin, urlparse, urldefrag
import requests
import trafilatura
from bs4 import BeautifulSoup
from app.config import SEED_URLS, MAX_PAGES_PER_DOMAIN, REQUEST_DELAY_SECONDS, USER_AGENT

session = requests.Session()
session.headers.update({"User-Agent": USER_AGENT})

def robots_allowed(url: str) -> bool:
    parsed = urlparse(url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    parser = urllib.robotparser.RobotFileParser()
    parser.set_url(robots_url)
    try:
        parser.read()
        return parser.can_fetch(USER_AGENT, url)
    except Exception:
        # Fail closed: do not crawl when the site's policy cannot be checked.
        return False

def crawl(seed: str):
    domain = urlparse(seed).netloc
    queue, visited, documents = deque([seed]), set(), []
    while queue and len(visited) < MAX_PAGES_PER_DOMAIN:
        url = urldefrag(queue.popleft())[0]
        if url in visited or urlparse(url).netloc != domain:
            continue
        visited.add(url)
        if not robots_allowed(url):
            print(f"Skipping (robots disallow or unavailable): {url}")
            continue
        try:
            response = session.get(url, timeout=20)
            response.raise_for_status()
            if "text/html" not in response.headers.get("content-type", ""):
                continue
            soup = BeautifulSoup(response.text, "html.parser")
            title = soup.title.get_text(" ", strip=True) if soup.title else url
            content = trafilatura.extract(response.text, include_tables=True, include_links=False)
            if content and len(content.strip()) > 120:
                documents.append({"url": url, "title": title, "text": content.strip(), "domain": domain})
            for anchor in soup.select("a[href]"):
                target = urljoin(url, anchor.get("href", ""))
                parsed = urlparse(target)
                if parsed.scheme in ("http", "https") and parsed.netloc == domain:
                    target = urldefrag(target)[0]
                    if target not in visited:
                        queue.append(target)
        except Exception as exc:
            print(f"Page error {url}: {exc}")
        time.sleep(REQUEST_DELAY_SECONDS)
    return documents

def scrape_all():
    output = []
    for seed in SEED_URLS:
        print(f"Crawling {seed}")
        output.extend(crawl(seed))
    return output

import ipaddress
import socket
from urllib.parse import urljoin, urlparse

# Browser-like User-Agent so educational websites are less likely
# to reject the request as an obvious bot request.
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/153.0.0.0 Safari/537.36"
)

MAX_BYTES = 2 * 1024 * 1024


# ------------------------------------------------------------
# APPROVED EDUCATIONAL SOURCES
# ------------------------------------------------------------

ALLOWED_DOMAINS = {
    "worldhistory.org",
    "khanacademy.org",
}


def _base_domain(host):
    host = (host or "").lower().split(":")[0].rstrip(".")

    if host.startswith("www."):
        host = host[4:]

    return host


def _is_allowed_domain(host):
    host = _base_domain(host)

    return any(
        host == domain or host.endswith("." + domain)
        for domain in ALLOWED_DOMAINS
    )


# ------------------------------------------------------------
# URL VALIDATION
# ------------------------------------------------------------

def validate_public_url(url):
    parsed = urlparse(url.strip())

    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError(
            "Only valid http/https URLs are allowed."
        )

    host = parsed.hostname.lower()

    # Only approved educational websites.
    if not _is_allowed_domain(host):
        raise ValueError(
            "This website is not an approved educational source."
        )

    # Block local addresses.
    if host in {"localhost", "127.0.0.1", "::1"}:
        raise ValueError(
            "Localhost URLs are not allowed."
        )

    try:
        addresses = socket.getaddrinfo(host, None)

        for item in addresses:
            ip = ipaddress.ip_address(item[4][0])

            if (
                ip.is_private
                or ip.is_loopback
                or ip.is_link_local
                or ip.is_reserved
            ):
                raise ValueError(
                    "Private or local network URLs are not allowed."
                )

    except socket.gaierror as exc:
        raise ValueError(
            "The URL host could not be resolved."
        ) from exc

    return parsed


# ------------------------------------------------------------
# REQUEST SESSION
# ------------------------------------------------------------

def _make_session():
    import requests
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry

    session = requests.Session()

    retry = Retry(
        total=2,
        connect=2,
        read=2,
        backoff_factor=0.4,
        status_forcelist=(
            429,
            500,
            502,
            503,
            504,
        ),
        allowed_methods=frozenset({
            "GET",
            "HEAD"
        }),
        raise_on_status=False,
    )

    session.mount(
        "http://",
        HTTPAdapter(max_retries=retry)
    )

    session.mount(
        "https://",
        HTTPAdapter(max_retries=retry)
    )

    session.headers.update({
        "User-Agent": USER_AGENT,

        "Accept": (
            "text/html,"
            "application/xhtml+xml,"
            "application/xml;"
            "q=0.9,"
            "image/avif,"
            "image/webp,"
            "*/*;q=0.8"
        ),

        "Accept-Language": "en-US,en;q=0.9",

        "Accept-Encoding": (
            "gzip, deflate"
        ),

        "Connection": "keep-alive",

        "Upgrade-Insecure-Requests": "1",
    })

    return session


# ------------------------------------------------------------
# TEXT CLEANING
# ------------------------------------------------------------

def _clean_text(value):
    return " ".join(
        str(value or "").split()
    ).strip()


# ------------------------------------------------------------
# EMBEDDED JSON EXTRACTION
# ------------------------------------------------------------

def _extract_json_text(value, output):

    if isinstance(value, dict):

        for key, item in value.items():

            key_l = str(key).lower()

            if key_l in {
                "articlebody",
                "description",
                "headline",
                "text",
                "transcript",
                "body",
            }:

                if isinstance(item, str):

                    cleaned = _clean_text(item)

                    if len(cleaned) >= 20:
                        output.append(cleaned)

            else:
                _extract_json_text(
                    item,
                    output
                )

    elif isinstance(value, list):

        for item in value:
            _extract_json_text(
                item,
                output
            )


# ------------------------------------------------------------
# CONTENT EXTRACTION
# ------------------------------------------------------------

def _extract_content(soup):

    import json

    # Prefer the actual article/content area.
    container = (
        soup.find("article")
        or soup.find("main")
        or soup.select_one(
            "[role='main'], "
            ".article-content, "
            ".article-body, "
            ".post-content, "
            ".content-body, "
            ".lesson-content"
        )
        or soup.body
        or soup
    )

    # Remove website navigation and non-content elements.
    for tag in container.find_all([
        "script",
        "style",
        "noscript",
        "svg",
        "nav",
        "footer",
        "header",
        "form",
        "aside",
    ]):

        tag.decompose()

    lines = []

    # --------------------------------------------------------
    # HEADINGS
    # --------------------------------------------------------

    for node in container.find_all([
        "h1",
        "h2",
        "h3",
        "h4",
    ]):

        text = _clean_text(
            node.get_text(
                " ",
                strip=True
            )
        )

        if text and text not in lines:
            lines.append(text)

    # --------------------------------------------------------
    # PARAGRAPHS / LISTS / QUOTATIONS
    # --------------------------------------------------------

    for node in container.find_all([
        "p",
        "li",
        "blockquote",
    ]):

        text = _clean_text(
            node.get_text(
                " ",
                strip=True
            )
        )

        # Lower threshold than the old crawler.
        # This prevents useful short passages from being lost.
        if len(text) >= 20 and text not in lines:
            lines.append(text)

    # --------------------------------------------------------
    # EMBEDDED JSON FALLBACK
    # --------------------------------------------------------

    # Some educational websites store their article text in
    # JSON inside the HTML instead of ordinary paragraphs.

    if len(" ".join(lines)) < 500:

        json_lines = []

        for script in soup.find_all("script"):

            script_type = (
                script.get("type") or ""
            ).lower()

            raw = (
                script.string
                or script.get_text()
            )

            if not raw:
                continue

            script_id = str(
                script.get("id", "")
            ).lower()

            if (
                "json" not in script_type
                and "__next_data__" not in script_id
            ):
                continue

            try:
                data = json.loads(raw)

            except (
                TypeError,
                ValueError
            ):
                continue

            _extract_json_text(
                data,
                json_lines
            )

        for text in json_lines:

            if text not in lines:
                lines.append(text)

    # --------------------------------------------------------
    # META DESCRIPTION FALLBACK
    # --------------------------------------------------------

    if not lines:

        meta = soup.find(
            "meta",
            attrs={
                "name": "description"
            }
        )

        if meta and meta.get("content"):

            description = _clean_text(
                meta["content"]
            )

            if description:
                lines.append(description)

    return "\n".join(lines)[:200000]


# ------------------------------------------------------------
# FETCH PAGE
# ------------------------------------------------------------

def fetch_page(url):

    try:
        from bs4 import BeautifulSoup

    except ImportError as exc:

        raise RuntimeError(
            "Web crawler dependencies are missing. "
            "Run: pip install requests beautifulsoup4"
        ) from exc

    validate_public_url(url)

    session = _make_session()

    try:

        response = session.get(
            url,
            timeout=(8, 20),
            allow_redirects=True,
            stream=True,
        )

        # Retry once using a normal Edge-like browser identity
        # if the first request is rejected.
        if response.status_code in (
            403,
            406,
        ):

            response.close()

            session.headers["User-Agent"] = (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/153.0.0.0 Safari/537.36 "
                "Edg/153.0.0.0"
            )

            response = session.get(
                url,
                timeout=(8, 20),
                allow_redirects=True,
                stream=True,
            )

        response.raise_for_status()

        # ----------------------------------------------------
        # VALIDATE FINAL REDIRECT
        # ----------------------------------------------------

        final_parsed = urlparse(
            response.url
        )

        if not _is_allowed_domain(
            final_parsed.hostname
        ):

            raise ValueError(
                "The page redirected to a website "
                "outside the approved sources."
            )

        # ----------------------------------------------------
        # CHECK CONTENT TYPE
        # ----------------------------------------------------

        content_type = (
            response.headers
            .get(
                "Content-Type",
                ""
            )
            .lower()
        )

        if (
            "text/html" not in content_type
            and
            "application/xhtml+xml"
            not in content_type
        ):

            raise ValueError(
                "The selected resource is not an HTML page."
            )

        # ----------------------------------------------------
        # READ RESPONSE SAFELY
        # ----------------------------------------------------

        data = bytearray()

        for chunk in response.iter_content(
            chunk_size=32768
        ):

            if not chunk:
                continue

            data.extend(chunk)

            if len(data) > MAX_BYTES:

                raise ValueError(
                    "Page is larger than "
                    "the 2 MB crawler limit."
                )

        encoding = (
            response.encoding
            or response.apparent_encoding
            or "utf-8"
        )

        response.close()

        html = bytes(data).decode(
            encoding,
            errors="replace"
        )

        # ----------------------------------------------------
        # PARSE HTML
        # ----------------------------------------------------

        soup = BeautifulSoup(
            html,
            "html.parser"
        )

        # ----------------------------------------------------
        # PAGE TITLE
        # ----------------------------------------------------

        title = ""

        if soup.title:

            title = _clean_text(
                soup.title.get_text(
                    " ",
                    strip=True
                )
            )

        if not title:

            heading = soup.find("h1")

            if heading:

                title = _clean_text(
                    heading.get_text(
                        " ",
                        strip=True
                    )
                )

        if not title:
            title = url

        # ----------------------------------------------------
        # EXTRACT CONTENT
        # ----------------------------------------------------

        content = _extract_content(
            soup
        )

        if len(content.strip()) < 80:

            raise ValueError(
                "The page was reached, but it did not contain "
                "enough readable educational text."
            )

        # ----------------------------------------------------
        # FIND SAME-SOURCE LINKS
        # ----------------------------------------------------

        links = []

        base_domain = _base_domain(
            final_parsed.hostname
        )

        for anchor in soup.find_all(
            "a",
            href=True
        ):

            target = (
                urljoin(
                    response.url,
                    anchor["href"]
                )
                .split("#")[0]
                .strip()
            )

            if not target:
                continue

            try:

                parsed = validate_public_url(
                    target
                )

            except ValueError:
                continue

            if (
                _base_domain(
                    parsed.hostname
                )
                ==
                base_domain
            ):

                links.append(
                    target
                )

        # Remove duplicates while preserving order.
        unique_links = list(
            dict.fromkeys(links)
        )[:10]

        return {
            "url": response.url,
            "title": title[:250],
            "content": content,
            "links": unique_links,
            "domain": base_domain,
        }

    finally:

        session.close()
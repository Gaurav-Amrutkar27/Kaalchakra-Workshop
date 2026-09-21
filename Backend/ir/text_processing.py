import math
import re
from collections import Counter

STOP_WORDS = {
    "a", "an", "the", "and", "or", "but", "if", "then", "than", "of", "to",
    "in", "on", "at", "for", "from", "by", "with", "as", "is", "are", "was",
    "were", "be", "been", "being", "this", "that", "these", "those", "it", "its",
    "they", "them", "their", "there", "here", "he", "she", "his", "her", "we", "you",
    "your", "our", "i", "me", "my", "do", "did", "does", "why", "what", "where", "when",
    "how", "who", "which", "can", "could", "would", "should", "will", "may", "might",
    "about", "into", "over", "after", "before", "also", "very", "more", "most", "some",
    "such", "each", "many", "other", "their", "through", "during", "because", "from"
}


def clean_text(value):
    if value is None:
        return ""
    text = str(value)
    text = re.sub(r"https?://\S+", " ", text)
    text = re.sub(r"[^\w\s'’-]", " ", text, flags=re.UNICODE)
    return re.sub(r"\s+", " ", text).strip()


def tokenize(text):
    text = clean_text(text).lower()
    words = re.findall(r"[a-zA-Z][a-zA-Z0-9'’-]*", text)
    return [w for w in words if w not in STOP_WORDS and len(w) > 1]


def split_passages(text, max_chars=420):
    """Turn authored/web text into readable retrieval passages."""
    raw = str(text or "").replace("\r", "\n")
    chunks = []
    for block in re.split(r"\n+", raw):
        block = re.sub(r"\s+", " ", block).strip()
        if not block:
            continue
        sentences = re.split(r"(?<=[.!?])\s+", block)
        current = ""
        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue
            candidate = (current + " " + sentence).strip()
            if len(candidate) <= max_chars:
                current = candidate
            else:
                if current:
                    chunks.append(current)
                current = sentence
        if current:
            chunks.append(current)
    return chunks


def tfidf_vectors(documents):
    """Return sparse TF-IDF vectors and IDF values for a list of strings."""
    token_lists = [tokenize(doc) for doc in documents]
    n = len(token_lists)
    df = Counter()
    for tokens in token_lists:
        df.update(set(tokens))
    idf = {term: math.log((1 + n) / (1 + freq)) + 1.0 for term, freq in df.items()}
    vectors = []
    for tokens in token_lists:
        counts = Counter(tokens)
        length = max(len(tokens), 1)
        vec = {}
        for term, count in counts.items():
            vec[term] = (count / length) * idf.get(term, 1.0)
        vectors.append(vec)
    return vectors, idf


def cosine_similarity(vec_a, vec_b):
    if not vec_a or not vec_b:
        return 0.0
    dot = sum(value * vec_b.get(term, 0.0) for term, value in vec_a.items())
    norm_a = math.sqrt(sum(v * v for v in vec_a.values()))
    norm_b = math.sqrt(sum(v * v for v in vec_b.values()))
    if not norm_a or not norm_b:
        return 0.0
    return dot / (norm_a * norm_b)


def query_vector(query, idf):
    tokens = tokenize(query)
    counts = Counter(tokens)
    length = max(len(tokens), 1)
    return {
        term: (count / length) * idf.get(term, 1.0)
        for term, count in counts.items()
    }

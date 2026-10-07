"""Pure-Python SimHash with CJK-aware features.

64-bit fingerprints with Hamming distance; used as dedup Level 3 (near-duplicate
detection) before the more expensive embedding cosine check. No numpy dependency
so it runs anywhere the backend runs.

Chinese text has no whitespace, so whitespace tokens would make one sentence a
single feature. CJK runs are therefore chopped into character bigrams; ASCII
words stay whole.
"""

import hashlib
import re

_CJK_RUN = re.compile(r"[\u4e00-\u9fff]+")
_TOKEN = re.compile(r"[A-Za-z0-9_]+")


def _features(text: str) -> dict[str, int]:
    text = text or ""
    features: dict[str, int] = {}
    for run in _CJK_RUN.findall(text):
        if len(run) == 1:
            features[run] = features.get(run, 0) + 1
            continue
        for i in range(len(run) - 1):
            bigram = run[i : i + 2]
            features[bigram] = features.get(bigram, 0) + 1
    for token in _TOKEN.findall(text.lower()):
        features[token] = features.get(token, 0) + 1
    return features


def simhash64(text: str) -> int:
    features = _features(text)
    if not features:
        return 0
    bits = [0] * 64
    for token, weight in features.items():
        digest = hashlib.md5(token.encode("utf-8")).digest()
        value = int.from_bytes(digest[:8], "big")
        for i in range(64):
            bits[i] += weight if (value >> i) & 1 else -weight
    fingerprint = 0
    for i, bit in enumerate(bits):
        if bit > 0:
            fingerprint |= 1 << i
    return fingerprint


def hamming_distance(left: int, right: int) -> int:
    return bin(left ^ right).count("1")


def is_near_duplicate(left: int | None, right: int | None, threshold: int = 12) -> bool:
    if not left or not right or left is None or right is None:
        return False
    return hamming_distance(left, right) <= threshold

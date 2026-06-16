"""
Semantic reconciliation of ARTICOL_EXTRA / ARTICOL_LIPSA within the same deviz.
Pairs unmatched articles and asks LLM if they could be the same article
(OCR variants, spelling differences, abbreviated denominations).

Supports both V1 holistic (neconformitati) and V2 holistic (ref_only/oferta_only).
"""
from __future__ import annotations
import json
from dataclasses import dataclass
from typing import Optional


@dataclass
class SemanticPair:
    deviz_cod: str
    deviz_den: str
    extra_cod: str
    extra_den: str
    extra_um: str
    extra_cant: float
    lipsa_cod: str
    lipsa_den: str
    lipsa_um: str
    lipsa_cant: float


@dataclass
class SemanticResult:
    pair: SemanticPair
    verdict: str          # "SAME" | "DIFFERENT" | "UNCERTAIN"
    reason: str
    error: Optional[str] = None


# ── Format detection + pair extraction ────────────────────────────────────────

def _is_v2(data: dict) -> bool:
    groups = data.get("matched_groups", [])
    return bool(groups) and "articole" in groups[0]


def _pairs_v1(data: dict) -> list[SemanticPair]:
    pairs = []
    for g in data.get("matched_groups", []):
        ncs = g.get("neconformitati", [])
        extras = [nc for nc in ncs
                  if nc.get("tip") == "ARTICOL_EXTRA" and not nc.get("is_component")]
        lipsas = [nc for nc in ncs
                  if nc.get("tip") == "ARTICOL_LIPSA" and not nc.get("is_component")]
        if not extras or not lipsas:
            continue
        deviz_cod = g.get("ref_deviz_cod") or g.get("oferta_deviz_cod") or ""
        deviz_den = g.get("deviz_denumire", deviz_cod)
        for e in extras:
            for l in lipsas:
                pairs.append(SemanticPair(
                    deviz_cod=deviz_cod, deviz_den=deviz_den,
                    extra_cod=e.get("oferta_cod", ""),
                    extra_den=e.get("oferta_denumire", ""),
                    extra_um=e.get("oferta_um", ""),
                    extra_cant=float(e.get("oferta_cantitate") or 0),
                    lipsa_cod=l.get("ref_cod", ""),
                    lipsa_den=l.get("ref_denumire", ""),
                    lipsa_um=l.get("ref_um", ""),
                    lipsa_cant=float(l.get("ref_cantitate") or 0),
                ))
    return pairs


def _pairs_v2(data: dict) -> list[SemanticPair]:
    pairs = []
    for g in data.get("matched_groups", []):
        extras = [a for a in g.get("oferta_only", []) if not a.get("is_component")]
        lipsas = [a for a in g.get("ref_only", []) if not a.get("is_component")]
        if not extras or not lipsas:
            continue
        deviz_cod = g.get("deviz_cod", "")
        deviz_den = g.get("deviz_den", deviz_cod)
        for e in extras:
            for l in lipsas:
                pairs.append(SemanticPair(
                    deviz_cod=deviz_cod, deviz_den=deviz_den,
                    extra_cod=e.get("cod", ""),
                    extra_den=e.get("denumire", ""),
                    extra_um=e.get("um", ""),
                    extra_cant=float(e.get("cantitate") or 0),
                    lipsa_cod=l.get("cod", ""),
                    lipsa_den=l.get("denumire", ""),
                    lipsa_um=l.get("um", ""),
                    lipsa_cant=float(l.get("cantitate") or 0),
                ))
    return pairs


def find_candidates(
    data: dict,
    max_per_deviz: int = 5,
    min_similarity: int = 25,
    max_total: int = 60,
) -> list[SemanticPair]:
    """
    Auto-detect holistic format and extract EXTRA+LIPSA pairs within same deviz.

    Rapidfuzz pre-filters by denomination similarity (min_similarity) and
    caps at max_per_deviz per deviz + max_total globally. This keeps LLM
    call count manageable (≤ max_total / BATCH_SIZE calls).
    """
    raw_pairs = _pairs_v2(data) if _is_v2(data) else _pairs_v1(data)
    if not raw_pairs:
        return []

    try:
        from rapidfuzz import fuzz as _fuzz

        def _sim(p: SemanticPair) -> int:
            return _fuzz.token_set_ratio(p.extra_den.lower(), p.lipsa_den.lower())
    except ImportError:
        def _sim(p: SemanticPair) -> int:  # type: ignore[misc]
            return 50  # neutral — pass all without fuzz

    # Group by deviz, score, filter low-similarity, cap per-deviz
    by_deviz: dict[str, list[tuple[int, SemanticPair]]] = {}
    for p in raw_pairs:
        key = p.deviz_cod or p.deviz_den
        score = _sim(p)
        if score >= min_similarity:
            by_deviz.setdefault(key, []).append((score, p))

    result: list[SemanticPair] = []
    for scored_pairs in by_deviz.values():
        top = sorted(scored_pairs, key=lambda x: x[0], reverse=True)[:max_per_deviz]
        result.extend(p for _, p in top)

    # Global cap: keep highest-scoring pairs first
    if len(result) > max_total:
        all_scored = [(
            _sim(p), p) for p in result
        ]
        all_scored.sort(key=lambda x: x[0], reverse=True)
        result = [p for _, p in all_scored[:max_total]]

    return result


# ── LLM analysis ──────────────────────────────────────────────────────────────

_BATCH_SIZE = 5


def _batch_prompt(pairs: list[SemanticPair]) -> str:
    lines = [
        "Ești expert în construcții. Analizează perechile de articole de deviz.",
        "Determină dacă EXTRA și LIPSĂ din fiecare pereche sunt același articol",
        "(diferență de OCR, abreviere, scriere) sau articole diferite.",
        "",
        f"Răspunde STRICT JSON array cu {len(pairs)} obiecte:",
        '[{"verdict": "SAME"|"DIFFERENT"|"UNCERTAIN", "reason": "max 8 cuvinte"}, ...]',
        "",
    ]
    for i, p in enumerate(pairs, 1):
        lines += [
            f"Pereche {i} — Deviz: {p.deviz_den}",
            f"  EXTRA (ofertă): cod={p.extra_cod!r}  den={p.extra_den!r}  um={p.extra_um}  cant={p.extra_cant}",
            f"  LIPSĂ (ref):    cod={p.lipsa_cod!r}  den={p.lipsa_den!r}  um={p.lipsa_um}  cant={p.lipsa_cant}",
            "",
        ]
    return "\n".join(lines)


def _parse_llm_json(raw: str) -> list[dict]:
    raw = raw.strip()
    # Strip markdown fences
    if raw.startswith("```"):
        raw = "\n".join(raw.split("\n")[1:])
    if raw.endswith("```"):
        raw = "\n".join(raw.split("\n")[:-1])
    raw = raw.strip()
    # Find first '[' to skip preamble text
    idx = raw.find("[")
    if idx > 0:
        raw = raw[idx:]
    return json.loads(raw)


def analyze_pairs(
    pairs: list[SemanticPair],
    llm_client,
    model: str,
    verbose: bool = False,
) -> list[SemanticResult]:
    """Call LLM in batches of _BATCH_SIZE. Returns SemanticResult per pair."""
    results: list[SemanticResult] = []
    total = len(pairs)
    for start in range(0, total, _BATCH_SIZE):
        batch = pairs[start: start + _BATCH_SIZE]
        if verbose:
            print(f"  [semantic] Batch {start // _BATCH_SIZE + 1} ({start+1}-{min(start+len(batch), total)}/{total})")
        prompt = _batch_prompt(batch)
        try:
            resp = llm_client.chat.completions.create(
                model=model,
                max_tokens=512,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = resp.choices[0].message.content
            verdicts = _parse_llm_json(raw)
            for pair, v in zip(batch, verdicts):
                results.append(SemanticResult(
                    pair=pair,
                    verdict=v.get("verdict", "UNCERTAIN"),
                    reason=v.get("reason", ""),
                ))
        except Exception as exc:
            for pair in batch:
                results.append(SemanticResult(
                    pair=pair, verdict="UNCERTAIN", reason="",
                    error=str(exc)[:100],
                ))
    return results


# ── Summary helpers ────────────────────────────────────────────────────────────

def summarize(results: list[SemanticResult]) -> dict:
    same = [r for r in results if r.verdict == "SAME"]
    diff = [r for r in results if r.verdict == "DIFFERENT"]
    unc  = [r for r in results if r.verdict == "UNCERTAIN"]
    err  = [r for r in results if r.error]
    return {
        "total_pairs": len(results),
        "SAME": len(same),
        "DIFFERENT": len(diff),
        "UNCERTAIN": len(unc),
        "errors": len(err),
        "same_pairs": [
            {
                "deviz": r.pair.deviz_den,
                "extra_cod": r.pair.extra_cod,
                "extra_den": r.pair.extra_den,
                "lipsa_cod": r.pair.lipsa_cod,
                "lipsa_den": r.pair.lipsa_den,
                "reason": r.reason,
            }
            for r in same
        ],
    }

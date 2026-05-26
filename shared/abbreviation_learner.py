"""
LLM-based abbreviation learner pentru DESCRIERE_DIFERITA borderline.

Flux:
  1. Citește holistic_oferta_N.json → extrage DD cu sim 0.25-0.55
  2. Filtrează perechile deja cunoscute
  3. Trimite batch la Claude Haiku pentru validare DA/NU
  4. Salvează perechile confirmate în learned_abbreviations.json
  5. Returnează statistici

Utilizare:
  python3 -m shared.abbreviation_learner --client "Scoala Dragomiresti"
  sau din Python:
    from shared.abbreviation_learner import learn_from_client
    stats = learn_from_client("Scoala Dragomiresti")
"""

import json
import logging
import os
import re
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Prag Jaccard borderline: sub 0.55 dar peste 0.25 → trimiți la LLM
BORDERLINE_LOW = 0.25
BORDERLINE_HIGH = 0.55

# Dimensiune batch LLM (perechi per apel API)
BATCH_SIZE = 20


def _get_anthropic_client():
    """Inițializează clientul Anthropic cu config din environment."""
    import anthropic
    base_url = os.environ.get("ANTHROPIC_BASE_URL")
    api_key = os.environ.get("ANTHROPIC_API_KEY", "dummy")
    if base_url:
        return anthropic.Anthropic(base_url=base_url, api_key=api_key)
    return anthropic.Anthropic(api_key=api_key)


def _collect_borderline_pairs(client_name: str) -> list[dict]:
    """
    Colectează perechile DESCRIERE_DIFERITA borderline din JSON-urile de comparație.
    Returnează lista de {ref, oferta, sim, oferta_nr, ref_cod}.
    """
    from shared.client_config import detect_clients, ClientConfig

    clients = detect_clients()
    cfg = next((c for c in clients if c.name == client_name), None)
    if not cfg:
        logger.error(f"[LEARNER] Client '{client_name}' negăsit")
        return []

    pairs = []
    for i in range(1, 10):
        f = cfg.output_dir / f"holistic_oferta_{i}.json"
        if not f.exists():
            continue
        holistic = json.loads(f.read_text(encoding="utf-8"))
        for mg in holistic.get("matched_groups", []):
            for nc in mg.get("neconformitati", []):
                if nc.get("tip") != "DESCRIERE_DIFERITA":
                    continue
                sim = nc.get("similaritate", 0)
                if BORDERLINE_LOW <= sim <= BORDERLINE_HIGH:
                    pairs.append({
                        "ref": nc.get("ref", ""),
                        "oferta": nc.get("oferta", ""),
                        "sim": sim,
                        "oferta_nr": i,
                        "ref_cod": nc.get("ref_cod", ""),
                    })

    logger.info(f"[LEARNER] {client_name}: {len(pairs)} perechi borderline (sim {BORDERLINE_LOW}-{BORDERLINE_HIGH})")
    return pairs


def _filter_already_known(pairs: list[dict]) -> list[dict]:
    """Elimină perechile deja cunoscute (din dict static sau learned)."""
    from shared.abbreviations import are_learned_equivalent, expand_abbreviations

    filtered = []
    for p in pairs:
        ref_exp = expand_abbreviations(p["ref"])
        of_exp = expand_abbreviations(p["oferta"])
        # Dacă după expandare devin identice → deja rezolvate de dict static
        if ref_exp.strip() == of_exp.strip():
            continue
        # Dacă LLM a confirmat deja echivalența
        if are_learned_equivalent(p["ref"], p["oferta"]):
            continue
        filtered.append(p)

    logger.info(f"[LEARNER] {len(filtered)} perechi noi după filtrare known")
    return filtered


def _validate_batch_with_llm(pairs: list[dict], client) -> dict[str, str]:
    """
    Trimite un batch de perechi la Claude Haiku pentru validare DA/NU.
    Returnează dict {key: "DA"/"NU"} unde key = "ref|||oferta".
    """
    if not pairs:
        return {}

    # Construiește prompt
    lines = []
    for i, p in enumerate(pairs, 1):
        lines.append(f"{i}. REF: \"{p['ref'][:100]}\"\n   OF:  \"{p['oferta'][:100]}\"")

    prompt = """Ești expert în devize de construcții românești.

Verifică dacă fiecare pereche de denumiri de articol descrie ACELAȘI articol tehnic,
chiar dacă există diferențe de ortografie, abrevieri sau formulare ușor diferită.

Răspunde EXACT cu un JSON array de obiecte: [{"nr": 1, "echivalent": true/false}, ...]
Nu adăuga explicații, doar JSON-ul.

Perechi de verificat:
""" + "\n".join(lines)

    try:
        model = os.environ.get("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")
        response = client.messages.create(
            model=model,
            max_tokens=512,
            messages=[{"role": "user", "content": prompt}]
        )
        text = response.content[0].text.strip()

        # Extrage JSON din răspuns (poate fi înconjurat de ```json```)
        m = re.search(r'\[.*?\]', text, re.DOTALL)
        if not m:
            logger.warning(f"[LEARNER] LLM răspuns invalid: {text[:100]}")
            return {}

        results = json.loads(m.group(0))
        equivalences = {}
        for r in results:
            nr = r.get("nr", 0) - 1
            if 0 <= nr < len(pairs) and r.get("echivalent"):
                p = pairs[nr]
                key = f"{p['ref'].lower().strip()}|||{p['oferta'].lower().strip()}"
                equivalences[key] = "echivalent"

        logger.info(f"[LEARNER] LLM: {len(equivalences)}/{len(pairs)} perechi confirmate echivalente")
        return equivalences

    except Exception as e:
        logger.error(f"[LEARNER] Eroare LLM: {e}")
        return {}


def learn_from_client(client_name: str, dry_run: bool = False) -> dict:
    """
    Procesul complet de învățare pentru un client.

    Args:
        client_name: Numele clientului (ex: "Scoala Dragomiresti")
        dry_run: Dacă True, nu salvează în fișier

    Returns:
        Statistici: {total_borderline, filtered, validated, new_equivalences}
    """
    from shared.abbreviations import save_learned_pairs, reload_learned_cache

    pairs = _collect_borderline_pairs(client_name)
    if not pairs:
        return {"total_borderline": 0, "filtered": 0, "validated": 0, "new_equivalences": 0}

    filtered = _filter_already_known(pairs)
    if not filtered:
        return {"total_borderline": len(pairs), "filtered": 0, "validated": 0, "new_equivalences": 0}

    # Procesează în batch-uri
    client = _get_anthropic_client()
    all_equivalences = {}
    for i in range(0, len(filtered), BATCH_SIZE):
        batch = filtered[i:i + BATCH_SIZE]
        logger.info(f"[LEARNER] Batch {i//BATCH_SIZE + 1}: {len(batch)} perechi → LLM")
        eq = _validate_batch_with_llm(batch, client)
        all_equivalences.update(eq)

    if not dry_run and all_equivalences:
        save_learned_pairs(all_equivalences)
        reload_learned_cache()

    return {
        "total_borderline": len(pairs),
        "filtered": len(filtered),
        "validated": len(filtered),
        "new_equivalences": len(all_equivalences),
        "dry_run": dry_run,
    }


def learn_all_clients(dry_run: bool = False) -> dict:
    """Rulează learn_from_client pentru toți clienții detectați."""
    from shared.client_config import detect_clients
    clients = detect_clients()
    total = {}
    for cfg in clients:
        logger.info(f"[LEARNER] === {cfg.name} ===")
        stats = learn_from_client(cfg.name, dry_run=dry_run)
        total[cfg.name] = stats
    return total


if __name__ == "__main__":
    import argparse
    logging.basicConfig(level=logging.INFO)

    parser = argparse.ArgumentParser(description="Învață abrevieri din DESCRIERE_DIFERITA borderline")
    parser.add_argument("--client", help="Numele clientului (dacă lipsește, procesează toți)")
    parser.add_argument("--dry-run", action="store_true", help="Nu salvează în fișier")
    parser.add_argument("--show", action="store_true", help="Afișează perechile borderline fără LLM")
    args = parser.parse_args()

    if args.show:
        name = args.client or "Scoala Dragomiresti"
        pairs = _collect_borderline_pairs(name)
        filtered = _filter_already_known(pairs)
        print(f"\nPerechi borderline pentru {name}: {len(pairs)} total, {len(filtered)} noi\n")
        for p in filtered[:20]:
            print(f"  [{p['oferta_nr']} {p['ref_cod']}] sim={p['sim']}")
            print(f"    REF: {p['ref'][:80]}")
            print(f"    OF:  {p['oferta'][:80]}")
            print()
    elif args.client:
        stats = learn_from_client(args.client, dry_run=args.dry_run)
        print(f"\nRezultat pentru {args.client}:")
        print(json.dumps(stats, indent=2, ensure_ascii=False))
    else:
        stats = learn_all_clients(dry_run=args.dry_run)
        print("\nRezultat total:")
        print(json.dumps(stats, indent=2, ensure_ascii=False))

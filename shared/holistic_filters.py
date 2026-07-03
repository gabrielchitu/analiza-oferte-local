"""Filters applied to holistic data before report generation.

CODELESS placeholder articles (parser fallback for articles whose code
could not be read) have no code to compare against — listing them in
reports is pure noise. These filters drop them from the rendered output
without touching the holistic JSON on disk.
"""


def _is_codeless_nc(nc: dict) -> bool:
    return (str(nc.get("ref_cod") or "").startswith("CODELESS")
            or str(nc.get("oferta_cod") or "").startswith("CODELESS"))


def _is_codeless_art(art: dict) -> bool:
    return (str(art.get("cod") or "").startswith("CODELESS")
            or str(art.get("parent_cod") or "").startswith("CODELESS")
            or str(art.get("display_parent_cod") or "").startswith("CODELESS"))


def strip_codeless_ncs(ncs: list) -> list:
    """Return NC list without entries involving CODELESS placeholder codes."""
    return [nc for nc in (ncs or []) if not _is_codeless_nc(nc)]


def strip_codeless(holistic: dict) -> dict:
    """Return a copy of a holistic dict without CODELESS articles and their NCs.

    Non-mutating: group dicts are shallow-copied with filtered
    neconformitati / article lists; everything else is shared.
    """
    if not holistic:
        return holistic
    result = dict(holistic)
    for key in ("matched_groups", "ref_only_groups", "oferta_only_groups"):
        groups = holistic.get(key)
        if not isinstance(groups, list):
            continue
        new_groups = []
        for g in groups:
            g2 = dict(g)
            if isinstance(g2.get("neconformitati"), list):
                g2["neconformitati"] = strip_codeless_ncs(g2["neconformitati"])
            for akey in ("ref_articles", "oferta_articles", "articles"):
                if isinstance(g2.get(akey), list):
                    g2[akey] = [a for a in g2[akey] if not _is_codeless_art(a)]
            if isinstance(g2.get("matches"), list):
                g2["matches"] = [m for m in g2["matches"]
                                 if not (isinstance(m, dict) and _is_codeless_nc(m))]
            new_groups.append(g2)
        result[key] = new_groups
    return result

# Subcomponent Detection and Matching

## Comparison Modes

Run extraction with flexible subcomponent matching:

```bash
# Strict mode (default): validate cant+UM for all articles
python3 local_run.py --comp-mode strict

# Lenient mode: code-only matching for incomplete subcomponents
python3 local_run.py --comp-mode lenient
```

## Subcomponent Detection

Subcomponents are automatically detected from:
- Explicit markers: `>>> componenta 0C1`, `>>> component 002`
- Suffix pattern: `.L` (e.g., `17.L`, `19.L`)
- Hierarchy: Numeric hierarchy like `1.1`, `2.3` under parent `1`, `2`

Detected subcomponents are marked in output with `"is_component": true` and visually distinct in DOCX reports:
- [Subcomponent] badge in code column
- Light gray background
- Indented description

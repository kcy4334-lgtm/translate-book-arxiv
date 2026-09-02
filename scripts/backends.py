#!/usr/bin/env python3
"""
backends.py - Choose how a source document becomes markdown.

Two backends exist:

  calibre  Calibre HTMLZ -> pandoc. Works for any PDF/DOCX/EPUB, but PDF input
           goes through pdftohtml, which destroys math irrecoverably.
  arxiv    Fetch the paper's LaTeX source from arXiv and convert that. Math and
           figure captions survive because nothing round-trips through pixels.

Downstream stages depend only on the temp-dir contract (input.md + images/),
so the two backends are interchangeable from chunking onwards.
"""

import os
import sys

import arxiv_backend

# config.txt values. 'calibre_htmlz' is the legacy spelling written by older
# versions and is treated as 'calibre' so existing temp dirs stay resumable.
BACKEND_CALIBRE = 'calibre'
BACKEND_ARXIV = 'arxiv'
_LEGACY_ALIASES = {'calibre_htmlz': BACKEND_CALIBRE}


def normalize_backend_name(value):
    if not value:
        return None
    value = value.strip()
    return _LEGACY_ALIASES.get(value, value)


def select_backend(input_file, requested, arxiv_id_override, allow_network):
    """Return (backend, arxiv_id_or_None, reason).

    Raises SystemExit when the user explicitly asked for something impossible,
    so a silent downgrade can never happen behind their back.
    """
    if arxiv_id_override:
        normalized = arxiv_backend.normalize_arxiv_id(arxiv_id_override)
        if not normalized:
            raise SystemExit(f"Error: could not parse --arxiv-id {arxiv_id_override!r}")
        if not allow_network:
            raise SystemExit(
                f"Error: --arxiv-id needs network access.\n"
                f"  Re-run with --allow-network, or download\n"
                f"  https://arxiv.org/e-print/{normalized}\n"
                f"  yourself and use --backend calibre for a local-only run."
            )
        return BACKEND_ARXIV, normalized, 'explicit --arxiv-id'

    if requested == BACKEND_CALIBRE:
        return BACKEND_CALIBRE, None, 'explicit --backend calibre'

    if os.path.splitext(input_file)[1].lower() != '.pdf':
        if requested == BACKEND_ARXIV:
            raise SystemExit("Error: --backend arxiv requires a PDF input.")
        return BACKEND_CALIBRE, None, 'non-PDF input'

    arxiv_id, signals = arxiv_backend.detect_arxiv_id(input_file)

    if requested == BACKEND_ARXIV:
        if not arxiv_id:
            raise SystemExit(
                f"Error: --backend arxiv but no arXiv id found ({signals}).\n"
                f"  Pass --arxiv-id <id> explicitly."
            )
        if not allow_network:
            raise SystemExit(
                f"Error: the arXiv backend needs network access.\n"
                f"  Re-run with --allow-network, or fetch\n"
                f"  https://arxiv.org/e-print/{arxiv_id}\n"
                f"  yourself and use --backend calibre for a local-only run."
            )
        return BACKEND_ARXIV, arxiv_id, f'detected {arxiv_id} via {signals}'

    # auto
    if arxiv_id and allow_network:
        return BACKEND_ARXIV, arxiv_id, f'auto: detected {arxiv_id} via {signals}'
    if arxiv_id:
        print(f"Note: this looks like arXiv paper {arxiv_id}, whose LaTeX source "
              f"would preserve equations and figures.")
        print("      Re-run with --allow-network to use it.")
        return BACKEND_CALIBRE, arxiv_id, 'auto: arXiv detected but no --allow-network'
    return BACKEND_CALIBRE, None, f'auto: {signals}'


def check_backend_switch(temp_dir, backend):
    """Return an error message if temp_dir was built by a different backend.

    Mixing an arXiv-derived input.md with calibre-derived images/ (or stale
    chunks from the other backend) produces silent corruption, so this is a
    hard stop rather than a warning.
    """
    config_path = os.path.join(temp_dir, 'config.txt')
    if not os.path.exists(config_path):
        return None

    recorded = None
    try:
        with open(config_path, encoding='utf-8') as f:
            for line in f:
                if line.strip().startswith('#') or '=' not in line:
                    continue
                key, value = line.strip().split('=', 1)
                if key == 'conversion_method':
                    recorded = normalize_backend_name(value)
                    break
    except OSError:
        return None

    if not recorded or recorded == backend:
        return None

    input_md = os.path.join(temp_dir, 'input.md')
    if not os.path.exists(input_md):
        return None

    return (
        f"Backend mismatch: {os.path.basename(temp_dir)} was built with "
        f"'{recorded}' but '{backend}' was requested.\n"
        f"  Reusing it would mix incompatible input.md and images/.\n"
        f"  fix: delete {temp_dir}, or pass a fresh --temp-root, "
        f"or re-run with --backend {recorded}"
    )


def abort_on_backend_switch(message):
    if message:
        print(f"Error: {message}", file=sys.stderr)
        sys.exit(1)

#!/usr/bin/env python3
"""Fetch a corpus of real government PDFs for the corpus tests.

The PDFs are **not committed**: they are third-party documents, they are large,
and the repository should stay cloneable. This script reproduces the corpus
instead. It is deliberately explicit about every URL so the corpus is auditable.

Usage::

    python scripts/fetch_corpus.py --out corpus
    PDFUA_CORPUS=corpus pytest tests/test_real_documents.py

Environment notes
-----------------
Some ``.gov`` hostnames are unreachable through a poisoned system resolver on
some networks (observed on an Indonesian ISP: ``www.irs.gov``, ``www.cdc.gov``
and ``www.ssa.gov`` did not resolve, but existed and answered over DoH). A
connection failure is therefore **not** evidence that a document does not exist,
and this script says so rather than reporting a clean "404".

If the system resolver fails, pass ``--doh`` to resolve over DNS-over-HTTPS and
connect by address with SNI preserved, which is what the development corpus used.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)

#: Documents chosen for format diversity: forms, publications, statutes,
#: regulations, budgets, congressional reports, and the ADA rule itself.
SOURCES: tuple[str, ...] = (
    "https://www.irs.gov/pub/irs-pdf/f1040.pdf",
    "https://www.irs.gov/pub/irs-pdf/p15.pdf",
    "https://www.irs.gov/pub/irs-pdf/fw9.pdf",
    "https://www.irs.gov/pub/irs-pdf/p1.pdf",
    "https://www.govinfo.gov/content/pkg/PLAW-117publ58/pdf/PLAW-117publ58.pdf",
    "https://www.govinfo.gov/content/pkg/CFR-2023-title1-vol1/pdf/CFR-2023-title1-vol1.pdf",
    "https://www.govinfo.gov/content/pkg/USCODE-2022-title42/pdf/USCODE-2022-title42-chap126.pdf",
    "https://www.govinfo.gov/content/pkg/BUDGET-2024-BUD/pdf/BUDGET-2024-BUD.pdf",
    "https://www.govinfo.gov/content/pkg/FR-2024-04-24/pdf/2024-07758.pdf",
    "https://www.govinfo.gov/content/pkg/CRPT-118hrpt1/pdf/CRPT-118hrpt1.pdf",
    "https://www.govinfo.gov/content/pkg/CHRG-117hhrg48055/pdf/CHRG-117hhrg48055.pdf",
    "https://www.govinfo.gov/content/pkg/CFR-2023-title29-vol4/pdf/CFR-2023-title29-vol4.pdf",
    "https://www.ada.gov/assets/pdfs/web-rule.pdf",
)

DOH_ENDPOINT = "https://cloudflare-dns.com/dns-query"


@dataclass(frozen=True, slots=True)
class Fetched:
    """One attempted download."""

    url: str
    path: Path | None
    status: str
    bytes_written: int
    sha256: str


def _slug(url: str) -> str:
    name = Path(urllib.parse.urlparse(url).path).name or "index"
    digest = hashlib.sha256(url.encode()).hexdigest()[:8]
    return f"{name}-{digest}.pdf"


def resolve_over_doh(host: str) -> list[str]:
    """Resolve ``host`` to A records using DNS-over-HTTPS.

    Returns:
        The addresses, or an empty list if the lookup failed.
    """
    request = urllib.request.Request(
        f"{DOH_ENDPOINT}?name={host}&type=A",
        headers={"Accept": "application/dns-json", "User-Agent": USER_AGENT},
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            payload = json.loads(response.read())
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        return []
    return [answer["data"] for answer in payload.get("Answer", []) if answer.get("type") == 1]


def fetch(url: str, *, use_doh: bool, timeout: int = 60) -> bytes:
    """Download ``url``.

    Raises:
        urllib.error.URLError: if the request fails for any reason.
    """
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    if not use_doh:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return bytes(response.read())

    host = urllib.parse.urlparse(url).hostname
    if host is None:
        raise urllib.error.URLError(f"no host in {url}")
    addresses = resolve_over_doh(host)
    if not addresses:
        raise urllib.error.URLError(f"DoH could not resolve {host}")
    # urllib cannot pin an address while keeping SNI, so this path is documented
    # as requiring curl. Fail loudly rather than silently falling back to the
    # system resolver, which is the thing known to be lying.
    raise urllib.error.URLError(
        f"DoH mode needs curl for {host} ({addresses[0]}); "
        f"run: curl --resolve {host}:443:{addresses[0]} -A '<ua>' -L {url}"
    )


def main(argv: list[str] | None = None) -> int:
    """Fetch the corpus and write a manifest. Returns a process exit code."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=Path("corpus"))
    parser.add_argument(
        "--doh",
        action="store_true",
        help="resolve over DoH (prints the curl command when the system resolver is lying)",
    )
    parser.add_argument("--timeout", type=int, default=60)
    args = parser.parse_args(argv)

    args.out.mkdir(parents=True, exist_ok=True)
    results: list[Fetched] = []

    for url in SOURCES:
        target = args.out / _slug(url)
        if target.exists() and target.read_bytes()[:5] == b"%PDF-":
            digest = hashlib.sha256(target.read_bytes()).hexdigest()
            results.append(Fetched(url, target, "cached", target.stat().st_size, digest))
            print(f"cached   {target.name}")
            continue
        try:
            payload = fetch(url, use_doh=args.doh, timeout=args.timeout)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            results.append(Fetched(url, None, f"failed: {exc}", 0, ""))
            print(f"FAILED   {url}\n         {exc}", file=sys.stderr)
            continue
        if payload[:5] != b"%PDF-":
            results.append(Fetched(url, None, "not a PDF", len(payload), ""))
            print(f"NOT-PDF  {url} ({len(payload)} bytes, not a PDF)", file=sys.stderr)
            continue
        target.write_bytes(payload)
        digest = hashlib.sha256(payload).hexdigest()
        results.append(Fetched(url, target, "ok", len(payload), digest))
        print(f"ok       {target.name} ({len(payload):,} bytes)")

    manifest = [
        {
            "url": r.url,
            "file": r.path.name if r.path else None,
            "status": r.status,
            "bytes": r.bytes_written,
            "sha256": r.sha256,
        }
        for r in results
    ]
    (args.out / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    ok = sum(1 for r in results if r.status in {"ok", "cached"})
    total = sum(r.bytes_written for r in results)
    print(f"\n{ok}/{len(results)} documents, {total / 1_000_000:.1f} MB")
    print("A failure above may be DNS poisoning, not absence — see the module docstring.")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

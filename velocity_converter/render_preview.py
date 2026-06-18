#!/usr/bin/env python3
"""Ad-hoc rendering preview against a live Socotra EC tenant.

Posts a Velocity template to `POST {API_URL}document/{tenantLocator}/documents/render`
(docs.socotra.com Documents API, "Ad-hoc Rendering") and returns the rendered
document — no transaction needed. The deployed DocumentDataSnapshotPlugin on the
tenant supplies `$data` (conditionals included), so deploy the generated plugin
before previewing templates that use `$data.condN`.

Everything travels as multipart/form-data (mirrors the known-working Postman call):
    referenceType    quote | policy | invoice | transaction | segment | term
    referenceLocator locator of the live entity to render against
    templateFormat   velocity
    documentConfig   inline DocumentConfigRef JSON — self-sufficient, the named
                     document config does NOT need to be deployed on the tenant
    productName      e.g. ZenCover
    template         the Velocity template source itself

Usage:
    python3 -m velocity_converter.render_preview \
        --template workspace/output/<stem>/<stem>.final.vm \
        --reference-type quote --reference-locator <locator> \
        [--out workspace/output/<stem>/<stem>.preview.pdf] [--open] [--reveal]

`--open` pops the saved PDF open in the OS viewer; `--reveal` selects it in
Finder/Explorer. Both require `--out` (there must be a file on disk to show). The
call prints a short progress trace to stderr so a demo can watch the API work.

Credentials come from environment variables, with a gitignored `.env.ai-documents`
at the repo root as the fallback (copy `.env.ai-documents.example`):
    AI_DOCUMENTS_API_URL          EC API base URL (trailing slash optional)
    AI_DOCUMENTS_TENANT_LOCATOR   tenant UUID
    AI_DOCUMENTS_PAT              PAT (or JWT) with documents:render-external
    AI_DOCUMENTS_PRODUCT_NAME     optional default for --product-name
    AI_DOCUMENTS_REFERENCE_<TYPE> optional locator per reference type, used by
                                  the test suite (e.g. AI_DOCUMENTS_REFERENCE_QUOTE)
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
import uuid
from pathlib import Path

REFERENCE_TYPES = ("quote", "policy", "invoice", "transaction", "segment", "term")
ENV_PREFIX = "AI_DOCUMENTS_"
ENV_FILE = ".env.ai-documents"

DEFAULT_DOCUMENT_CONFIG = {
    "name": "SimpleForm",
    "scope": "term",
    "format": "pdf",
    "rendering": "dynamic",
    "trigger": "issued",
    "portrait": True,
    "pageSize": "letter",
}


class RenderPreviewError(RuntimeError):
    """Raised when the render call fails (non-2xx or transport error)."""

    def __init__(self, message: str, status: int | None = None, body: str = ""):
        super().__init__(message)
        self.status = status
        self.body = body


def load_env(repo_root: Path | None = None) -> dict[str, str]:
    """Resolve AI_DOCUMENTS_* settings: process env wins over .env.ai-documents."""
    values: dict[str, str] = {}
    root = repo_root or Path(__file__).resolve().parent.parent
    env_file = root / ENV_FILE
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key, value = key.strip(), value.strip().strip('"').strip("'")
            if key.startswith(ENV_PREFIX):
                values[key] = value
    for key, value in os.environ.items():
        if key.startswith(ENV_PREFIX) and value:
            values[key] = value
    return values


def _encode_multipart(
    fields: dict[str, str],
    files: dict[str, tuple[str, str, bytes]] | None = None,
) -> tuple[bytes, str]:
    """Encode text fields (and optional file parts) as multipart/form-data.

    `files` maps a field name to (filename, content_type, content_bytes). File
    parts carry a `filename=` in their Content-Disposition, which is what makes
    the render endpoint treat the template as an uploaded "template file" rather
    than a plain string field.
    """
    boundary = f"----velocity-converter-{uuid.uuid4().hex}"
    chunks: list[bytes] = []
    for name, value in fields.items():
        chunks.append(
            (
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="{name}"\r\n'
                f"\r\n"
                f"{value}\r\n"
            ).encode("utf-8")
        )
    for name, (filename, ctype, content) in (files or {}).items():
        chunks.append(
            (
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'
                f"Content-Type: {ctype}\r\n"
                f"\r\n"
            ).encode("utf-8")
        )
        chunks.append(content)
        chunks.append(b"\r\n")
    chunks.append(f"--{boundary}--\r\n".encode("utf-8"))
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"


def render_template(
    api_url: str,
    tenant_locator: str,
    token: str,
    template_text: str,
    reference_type: str,
    reference_locator: str,
    *,
    product_name: str | None = None,
    document_config: dict | None = None,
    static_name: str | None = None,
    template_format: str = "velocity",
    timeout: int = 120,
) -> tuple[bytes, str]:
    """POST the template to the ad-hoc render endpoint.

    Returns (body bytes, content type) — the body is the rendered document in
    the format named by document_config (pdf bytes, html text, ...).
    Raises RenderPreviewError on transport failure or non-2xx response.
    """
    if reference_type not in REFERENCE_TYPES:
        raise ValueError(
            f"reference_type must be one of {REFERENCE_TYPES}, got {reference_type!r}"
        )

    fields = {
        "referenceType": reference_type,
        "referenceLocator": reference_locator,
        "templateFormat": template_format,
        "documentConfig": json.dumps(document_config or DEFAULT_DOCUMENT_CONFIG, indent=2),
    }
    if product_name:
        fields["productName"] = product_name
    if static_name:
        fields["staticName"] = static_name

    # The template must be uploaded as a file part (Content-Disposition with a
    # filename), not a plain string field — the endpoint rejects a bare
    # `template` text field with "template name or template file must be provided".
    files = {
        "template": (
            "template.vm",
            "text/plain; charset=utf-8",
            template_text.encode("utf-8"),
        )
    }

    url = f"{api_url.rstrip('/')}/document/{tenant_locator}/documents/render"
    body, content_type = _encode_multipart(fields, files)
    request = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": content_type,
            "Accept": "*/*",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read(), response.headers.get("Content-Type", "")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RenderPreviewError(
            f"render endpoint returned HTTP {exc.code}", status=exc.code, body=detail
        ) from exc
    except urllib.error.URLError as exc:
        raise RenderPreviewError(f"could not reach {url}: {exc.reason}") from exc


def require_settings(env: dict[str, str]) -> tuple[str, str, str]:
    """Pull (api_url, tenant_locator, token) from resolved env or fail loudly."""
    missing = [
        name for name in ("API_URL", "TENANT_LOCATOR", "PAT")
        if not env.get(f"{ENV_PREFIX}{name}")
    ]
    if missing:
        raise RenderPreviewError(
            "missing setting(s): "
            + ", ".join(f"{ENV_PREFIX}{n}" for n in missing)
            + f" — export them or fill in {ENV_FILE} (copy {ENV_FILE}.example)"
        )
    return (
        env[f"{ENV_PREFIX}API_URL"],
        env[f"{ENV_PREFIX}TENANT_LOCATOR"],
        env[f"{ENV_PREFIX}PAT"],
    )


def reveal_file(path: Path, *, reveal_in_folder: bool = False) -> bool:
    """Pop the rendered file open in the OS viewer (or reveal it in the folder).

    `reveal_in_folder=True` selects the file in Finder/Explorer instead of opening
    it. Returns True if a launcher was found and invoked, False otherwise (so the
    caller can fall back to just printing the path). Best-effort — never raises.
    """
    path = path.resolve()
    try:
        if sys.platform == "darwin":
            cmd = ["open", "-R", str(path)] if reveal_in_folder else ["open", str(path)]
        elif os.name == "nt":  # Windows
            if reveal_in_folder:
                cmd = ["explorer", "/select,", str(path)]
            else:  # os.startfile is the reliable open on Windows
                os.startfile(str(path))  # type: ignore[attr-defined]
                return True
        else:  # Linux / other — xdg-open has no "reveal", so open the parent dir
            opener = shutil.which("xdg-open")
            if not opener:
                return False
            target = path.parent if reveal_in_folder else path
            cmd = [opener, str(target)]
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except OSError:
        return False


def _human_size(n: int) -> str:
    size = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{int(size)} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Render a Velocity template ad-hoc against a live Socotra tenant."
    )
    parser.add_argument("--template", required=True, help="Path to the .vm template")
    parser.add_argument(
        "--reference-type", required=True, choices=REFERENCE_TYPES,
        help="Entity type the template renders against",
    )
    parser.add_argument(
        "--reference-locator", required=True,
        help="Locator of the quote/policy/segment/etc. to render against",
    )
    parser.add_argument(
        "--product-name",
        help=f"Product name (default: {ENV_PREFIX}PRODUCT_NAME from env)",
    )
    parser.add_argument(
        "--document-config",
        help="Path to a DocumentConfigRef JSON to send inline "
             "(default: built-in pdf/dynamic config)",
    )
    parser.add_argument("--out", help="Write rendered output here (default: stdout)")
    parser.add_argument(
        "--open", dest="open_after", action="store_true",
        help="Pop the rendered file open in the OS viewer after writing (needs --out)",
    )
    parser.add_argument(
        "--reveal", action="store_true",
        help="Reveal the rendered file in the folder (Finder/Explorer) after writing "
             "(needs --out)",
    )
    args = parser.parse_args()

    if (args.open_after or args.reveal) and not args.out:
        print("ERROR: --open/--reveal require --out (nothing on disk to show)",
              file=sys.stderr)
        sys.exit(2)

    env = load_env()
    try:
        api_url, tenant_locator, token = require_settings(env)
    except RenderPreviewError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(2)

    document_config = None
    if args.document_config:
        document_config = json.loads(
            Path(args.document_config).read_text(encoding="utf-8")
        )

    template_text = Path(args.template).read_text(encoding="utf-8")

    # A little theatre — show the call as it happens (stderr keeps stdout clean
    # for the piped-PDF case). This is the "watch the API work" beat in a demo.
    endpoint = f"{api_url.rstrip('/')}/document/{tenant_locator}/documents/render"
    print(f"→ POST {endpoint}", file=sys.stderr)
    print(f"  {args.reference_type}={args.reference_locator} · "
          f"template={Path(args.template).name} ({_human_size(len(template_text.encode()))})",
          file=sys.stderr)
    try:
        rendered, content_type = render_template(
            api_url=api_url,
            tenant_locator=tenant_locator,
            token=token,
            template_text=template_text,
            reference_type=args.reference_type,
            reference_locator=args.reference_locator,
            product_name=args.product_name or env.get(f"{ENV_PREFIX}PRODUCT_NAME"),
            document_config=document_config,
        )
    except RenderPreviewError as exc:
        print(f"✗ {exc}", file=sys.stderr)
        if exc.body:
            print(exc.body[:2000], file=sys.stderr)
        sys.exit(1)

    # The render endpoint returns the PDF with an empty Content-Type header; sniff
    # the magic bytes so the theatre line and write message read cleanly.
    if not content_type and rendered[:5] == b"%PDF-":
        content_type = "application/pdf (sniffed)"

    print(f"← 200 OK · {content_type or 'unknown type'} · "
          f"{_human_size(len(rendered))} received", file=sys.stderr)

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(rendered)
        print(f"✓ Rendered preview ({content_type or 'unknown type'}) written to {out_path}")
        if args.reveal:
            shown = reveal_file(out_path, reveal_in_folder=True)
            print("  revealed in folder" if shown
                  else "  (could not reveal — open it manually)", file=sys.stderr)
        if args.open_after:
            shown = reveal_file(out_path)
            print("  opened in default viewer" if shown
                  else "  (no OS opener found — open it manually)", file=sys.stderr)
    else:
        sys.stdout.buffer.write(rendered)


if __name__ == "__main__":
    main()

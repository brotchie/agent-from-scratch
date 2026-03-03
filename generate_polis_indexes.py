#!/usr/bin/env python3
"""
Generate showcase index pages for Polis submissions.

For each directory under `polis/` (recursive) that contains `afs.json`,
this script writes/overwrites `<that-dir>/index.html` with:
- Submitter and agent metadata
- Genesis snippet
- Extracted generated agent REPL from model response
- Agent description (markdown rendered offline)
- Image gallery
- Full transcript turns (user + agent), markdown rendered
- Root-level `polis.js` containing `const POLIS_LIST = [...]` for the main site

The generated HTML links to the shared site stylesheet (`styles.css`) for
visual consistency with the main site.
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

try:
    import markdown as markdown_lib
except ModuleNotFoundError as exc:
    raise SystemExit(
        "Missing dependency: markdown. Install it with: python3 -m pip install markdown"
    ) from exc

PYTHON_FENCE_RE = re.compile(r"```(?:python|py)\s*([\s\S]*?)```", re.IGNORECASE)
ANY_FENCE_RE = re.compile(r"```[\w+-]*\s*([\s\S]*?)```", re.IGNORECASE)


def rel_path(from_dir: Path, target: Path) -> str:
    return Path(os.path.relpath(target, from_dir)).as_posix()


def sanitize_href(value: str) -> str:
    href = value.strip()
    if not href:
        return "#"
    return html.escape(href, quote=True)


def render_markdown_offline(markdown_text: str) -> str:
    if markdown_text is None:
        return ""
    if not isinstance(markdown_text, str):
        markdown_text = str(markdown_text)
    return markdown_lib.markdown(
        markdown_text,
        extensions=[
            "extra",
            "sane_lists",
            "nl2br",
        ],
    )


def _collect_openai_content(content: Any, out: list[str]) -> None:
    if isinstance(content, str):
        if content.strip():
            out.append(content)
        return
    if not isinstance(content, list):
        return
    for part in content:
        if isinstance(part, str):
            if part.strip():
                out.append(part)
            continue
        if not isinstance(part, dict):
            continue
        for key in ("text", "content"):
            value = part.get(key)
            if isinstance(value, str) and value.strip():
                out.append(value)


def extract_model_text_candidates(model_response: Any) -> list[str]:
    candidates: list[str] = []
    parsed = model_response
    if isinstance(model_response, str):
        stripped = model_response.strip()
        if not stripped:
            return []
        try:
            parsed = json.loads(stripped)
        except Exception:
            return [model_response]

    if isinstance(parsed, dict):
        # OpenAI Chat Completions style.
        choices = parsed.get("choices")
        if isinstance(choices, list):
            for choice in choices:
                if not isinstance(choice, dict):
                    continue
                message = choice.get("message")
                if isinstance(message, dict):
                    _collect_openai_content(message.get("content"), candidates)
                text = choice.get("text")
                if isinstance(text, str) and text.strip():
                    candidates.append(text)

        # OpenAI Responses style.
        output = parsed.get("output")
        if isinstance(output, list):
            for item in output:
                if not isinstance(item, dict):
                    continue
                content = item.get("content")
                if isinstance(content, list):
                    for part in content:
                        if isinstance(part, dict):
                            text = part.get("text")
                            if isinstance(text, str) and text.strip():
                                candidates.append(text)
                text = item.get("text")
                if isinstance(text, str) and text.strip():
                    candidates.append(text)
        output_text = parsed.get("output_text")
        if isinstance(output_text, str) and output_text.strip():
            candidates.append(output_text)

        # Anthropic Messages style.
        content = parsed.get("content")
        if isinstance(content, list):
            for part in content:
                if isinstance(part, dict):
                    text = part.get("text")
                    if isinstance(text, str) and text.strip():
                        candidates.append(text)
                elif isinstance(part, str) and part.strip():
                    candidates.append(part)
        elif isinstance(content, str) and content.strip():
            candidates.append(content)
        completion = parsed.get("completion")
        if isinstance(completion, str) and completion.strip():
            candidates.append(completion)

        # Gemini GenerateContent style.
        gemini_candidates = parsed.get("candidates")
        if isinstance(gemini_candidates, list):
            for candidate in gemini_candidates:
                if not isinstance(candidate, dict):
                    continue
                content_obj = candidate.get("content")
                if isinstance(content_obj, dict):
                    parts = content_obj.get("parts")
                    if isinstance(parts, list):
                        for part in parts:
                            if isinstance(part, dict):
                                text = part.get("text")
                                if isinstance(text, str) and text.strip():
                                    candidates.append(text)
                candidate_output = candidate.get("output")
                if isinstance(candidate_output, str) and candidate_output.strip():
                    candidates.append(candidate_output)

    elif isinstance(parsed, list):
        for value in parsed:
            if isinstance(value, str) and value.strip():
                candidates.append(value)

    deduped: list[str] = []
    seen: set[str] = set()
    for text in candidates:
        if text in seen:
            continue
        seen.add(text)
        deduped.append(text)
    return deduped


def extract_python_code_block(text: str) -> str:
    source = text.strip()
    if not source:
        return ""

    match = PYTHON_FENCE_RE.search(source)
    if match:
        return match.group(1).strip()

    match = ANY_FENCE_RE.search(source)
    if match:
        return match.group(1).strip()

    for shebang in ("#!/usr/bin/env python3", "#!/usr/bin/python3"):
        index = source.find(shebang)
        if index != -1:
            return source[index:].strip()

    if source.startswith("#!/usr/bin/env python") or source.startswith("#!/usr/bin/python"):
        return source

    if "import " in source and ("def " in source or "if __name__" in source):
        return source

    return ""


def score_python_candidate(code: str) -> int:
    score = len(code.splitlines())
    if code.startswith("#!/usr/bin/env python3") or code.startswith("#!/usr/bin/python3"):
        score += 200
    if "if __name__ == \"__main__\":" in code or "if __name__ == '__main__':" in code:
        score += 80
    if "def " in code:
        score += 25
    if "import " in code:
        score += 20
    return score


def extract_generated_agent_repl(model_response: Any) -> str:
    text_candidates = extract_model_text_candidates(model_response)
    code_candidates: list[str] = []
    for text in text_candidates:
        code = extract_python_code_block(text)
        if code:
            code_candidates.append(code)

    if not code_candidates and isinstance(model_response, str):
        fallback_code = extract_python_code_block(model_response)
        if fallback_code:
            code_candidates.append(fallback_code)

    if not code_candidates:
        return ""
    return max(code_candidates, key=score_python_candidate)


def extract_model_name(data: dict[str, Any]) -> str:
    direct_keys = ("model_name", "model")
    for key in direct_keys:
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    parsed = data.get("model_response")
    if isinstance(parsed, str):
        stripped = parsed.strip()
        if stripped:
            try:
                parsed = json.loads(stripped)
            except Exception:
                parsed = None
        else:
            parsed = None

    if isinstance(parsed, dict):
        for key in ("model", "model_name", "modelVersion", "model_version"):
            value = parsed.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return "Unknown"


def make_meta_row(label: str, value_html: str) -> str:
    return (
        f'<div class="meta-row"><span class="meta-key">{html.escape(label, quote=False)}</span>'
        f'<span class="meta-value">{value_html}</span></div>'
    )


def normalize_twitter_link(raw_value: Any) -> tuple[str, str] | None:
    if raw_value is None:
        return None
    raw = str(raw_value).strip()
    if not raw:
        return None
    if raw.startswith(("http://", "https://")):
        return raw, raw
    handle = raw.lstrip("@")
    if not handle:
        return None
    return f"https://twitter.com/{handle}", f"@{handle}"


def normalize_github_link(raw_value: Any) -> tuple[str, str] | None:
    if raw_value is None:
        return None
    raw = str(raw_value).strip()
    if not raw:
        return None
    if raw.startswith(("http://", "https://")):
        return raw, raw
    username = raw.lstrip("@")
    if not username:
        return None
    return f"https://github.com/{username}", username


def render_external_link(url: str, label: str) -> str:
    return (
        f'<a class="meta-link" href="{sanitize_href(url)}" target="_blank" rel="noopener noreferrer">'
        f"{html.escape(label, quote=False)}</a>"
    )


def render_submitter_block(submitter: Any) -> str:
    if not isinstance(submitter, dict) or not submitter:
        return make_meta_row("Submitter", "Unknown")

    rows: list[str] = []
    twitter_link = normalize_twitter_link(submitter.get("twitter_handle"))
    if twitter_link is not None:
        rows.append(make_meta_row("Twitter", render_external_link(*twitter_link)))

    github_link = normalize_github_link(submitter.get("github_username"))
    if github_link is not None:
        rows.append(make_meta_row("GitHub", render_external_link(*github_link)))

    return "".join(rows) if rows else make_meta_row("Submitter", "Unknown")


def render_turns(turns: Any) -> str:
    if not isinstance(turns, list) or not turns:
        return '<p class="empty-note">No transcript turns provided.</p>'

    cards: list[str] = []
    for index, turn in enumerate(turns, start=1):
        turn_obj = turn if isinstance(turn, dict) else {"type": "unknown", "content": str(turn)}
        role_raw = str(turn_obj.get("type", "unknown")).strip().lower()
        role = "user" if role_raw == "user" else "agent" if role_raw == "agent" else "other"
        role_label = "User" if role == "user" else "Agent" if role == "agent" else role_raw.title() or "Turn"
        content = render_markdown_offline(str(turn_obj.get("content", "")))
        cards.append(
            "<article class=\"turn-card turn-{role}\">"
            "<div class=\"turn-header\">"
            "<span class=\"turn-role\">{role_label}</span>"
            "<span class=\"turn-index\">Turn {index}</span>"
            "</div>"
            "<div class=\"md-content\">{content}</div>"
            "</article>".format(
                role=role,
                role_label=html.escape(role_label, quote=False),
                index=index,
                content=content,
            )
        )
    return "\n".join(cards)


def render_gallery(images: Any) -> str:
    if not isinstance(images, list) or not images:
        return '<p class="empty-note">No gallery images listed.</p>'

    items: list[str] = []
    for image in images:
        if isinstance(image, dict):
            src = str(image.get("src", "")).strip()
            caption = str(image.get("caption", "")).strip()
        else:
            src = str(image).strip()
            caption = ""

        if not src:
            continue

        safe_src = sanitize_href(f"images/{src}")
        safe_caption = html.escape(caption, quote=False) if caption else ""
        safe_caption_attr = html.escape(caption, quote=True) if caption else ""
        safe_alt_attr = html.escape(caption or src, quote=True)
        figcaption = f"<figcaption>{safe_caption}</figcaption>" if safe_caption else ""
        items.append(
            f"<figure class=\"gallery-item\">"
            f"<button class=\"gallery-open\" type=\"button\" data-src=\"{safe_src}\" data-caption=\"{safe_caption_attr}\" "
            f"aria-label=\"Open image: {safe_alt_attr}\">"
            f"<img src=\"{safe_src}\" alt=\"{safe_alt_attr}\" loading=\"lazy\"></button>"
            f"{figcaption}</figure>"
        )

    return "<div class=\"gallery-grid\">" + "".join(items) + "</div>" if items else '<p class="empty-note">No gallery images listed.</p>'


def render_page(data: dict[str, Any], agent_dir: Path, repo_root: Path) -> str:
    agent_name = str(data.get("agent_name") or agent_dir.name)
    model_name = extract_model_name(data)
    genesis_snippet = str(data.get("genesis_snippet", ""))
    description_html = render_markdown_offline(str(data.get("agent_description_md", "")))
    generated_agent_repl = extract_generated_agent_repl(data.get("model_response"))
    turns_html = render_turns(data.get("turns", []))
    submitter_html = render_submitter_block(data.get("submitter"))
    gallery_html = render_gallery(data.get("images", []))

    styles_href = rel_path(agent_dir, repo_root / "styles.css")
    home_href = "/polis"

    total_turns = len(data.get("turns", [])) if isinstance(data.get("turns"), list) else 0
    title = html.escape(f"{agent_name} | Agent From Scratch", quote=True)

    return f"""<!DOCTYPE html>
<html lang="en" data-theme="terminal">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title}</title>
  <link rel="stylesheet" href="{html.escape(styles_href, quote=True)}">
  <style>
    .polis-page {{
      max-width: 980px;
      padding-top: 2rem;
      padding-bottom: 3rem;
    }}
    .polis-header {{
      margin-bottom: 1.5rem;
      text-align: center;
    }}
    .polis-header h1 {{
      font-size: clamp(1.8rem, 4vw, 2.5rem);
      margin-bottom: 0.5rem;
      letter-spacing: -0.02em;
    }}
    .polis-subtitle {{
      color: var(--text2);
      margin-bottom: 1rem;
      font-size: 0.95rem;
    }}
    .polis-back {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      padding: 0.45rem 0.9rem;
      border-radius: 999px;
      border: 1px solid var(--border);
      color: var(--accent);
      text-decoration: none;
      font-family: var(--font-code);
      font-size: 0.7rem;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      transition: border-color 0.2s, color 0.2s, box-shadow 0.2s;
    }}
    .polis-back:hover {{
      border-color: var(--accent);
      box-shadow: 0 0 14px var(--accent-dim);
    }}
    .polis-grid {{
      display: grid;
      gap: 1rem;
    }}
    .polis-page pre {{
      white-space: pre-wrap !important;
      overflow-wrap: anywhere;
      word-break: break-word;
      max-width: 100%;
    }}
    .polis-page pre[class*="language-"],
    .polis-page code[class*="language-"] {{
      white-space: pre-wrap !important;
      overflow-wrap: anywhere;
      word-break: break-word;
      color: #f4f7ff !important;
      font-size: 0.66rem !important;
      line-height: 1.3 !important;
      font-family: var(--font-code) !important;
      background: var(--bg) !important;
      text-shadow: none !important;
      -webkit-font-smoothing: antialiased;
    }}
    .polis-page pre[class*="language-"] > code[class*="language-"] {{
      white-space: inherit !important;
      word-break: inherit;
      overflow-wrap: inherit;
      color: inherit !important;
      text-shadow: none !important;
    }}
    .polis-page pre[class*="language-"] *,
    .polis-page code[class*="language-"] * {{
      text-shadow: none !important;
    }}
    .polis-card {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      padding: 1rem;
    }}
    .polis-card h2 {{
      font-family: var(--font-code);
      font-size: 0.82rem;
      text-transform: uppercase;
      letter-spacing: 0.09em;
      color: var(--text2);
      margin-bottom: 0.75rem;
    }}
    .meta-grid {{
      display: grid;
      gap: 0.45rem;
    }}
    .meta-row {{
      display: flex;
      justify-content: space-between;
      align-items: baseline;
      gap: 1rem;
      border-bottom: 1px dashed rgba(255, 255, 255, 0.08);
      padding-bottom: 0.3rem;
    }}
    .meta-key {{
      color: var(--text2);
      font-size: 0.78rem;
      font-family: var(--font-code);
      text-transform: uppercase;
      letter-spacing: 0.07em;
    }}
    .meta-value {{
      font-size: 0.86rem;
      color: var(--text);
      word-break: break-word;
    }}
    .meta-link {{
      color: var(--accent);
      text-decoration: underline;
      text-decoration-style: dashed;
      text-underline-offset: 2px;
      word-break: break-word;
    }}
    .meta-link:hover {{
      color: #7dfcc9;
    }}
    pre.polis-code {{
      margin: 0;
      padding: 0.95rem 1rem;
      border-radius: 10px;
      border: 1px solid var(--border);
      background: var(--bg);
      white-space: pre-wrap !important;
      word-break: break-word;
      overflow-wrap: anywhere;
      overflow-x: auto;
      font-size: 0.66rem;
      line-height: 1.35;
      font-family: var(--font-code);
      color: #f4f7ff;
      text-shadow: none !important;
      -webkit-font-smoothing: antialiased;
      font-variant-ligatures: none;
    }}
    .polis-code,
    .polis-code *,
    pre.polis-code[class*="language-"],
    pre.polis-code[class*="language-"] code[class*="language-"],
    .polis-code code[class*="language-"],
    .polis-code pre[class*="language-"] {{
      white-space: pre-wrap !important;
      overflow-wrap: anywhere;
      word-break: break-word;
      color: #f4f7ff !important;
      text-shadow: none !important;
      font-family: var(--font-code) !important;
    }}
    .polis-page .token {{
      color: inherit !important;
      background: transparent !important;
    }}
    .md-content {{
      color: var(--text);
      line-height: 1.6;
      font-size: 0.9rem;
      word-break: break-word;
    }}
    .md-content h1,
    .md-content h2,
    .md-content h3,
    .md-content h4,
    .md-content h5,
    .md-content h6 {{
      margin: 1rem 0 0.45rem;
      line-height: 1.3;
    }}
    .md-content p,
    .md-content ul,
    .md-content ol,
    .md-content blockquote,
    .md-content pre {{
      margin-bottom: 0.75rem;
    }}
    .md-content ul,
    .md-content ol {{
      padding-left: 1.3rem;
    }}
    .md-content a {{
      color: var(--accent);
      text-decoration: underline;
      text-decoration-style: dashed;
      text-underline-offset: 2px;
    }}
    .md-content blockquote {{
      border-left: 3px solid var(--border);
      padding-left: 0.8rem;
      color: var(--text2);
    }}
    .md-content img {{
      max-width: min(100%, 760px);
      max-height: 420px;
      width: auto;
      height: auto;
      object-fit: contain;
      display: block;
      margin: 0.6rem auto;
      border-radius: 8px;
      border: 1px solid var(--border);
      background: #090b12;
    }}
    .md-content code {{
      font-family: var(--font-code);
      background: var(--surface2);
      border: 1px solid rgba(255,255,255,0.06);
      padding: 0.05rem 0.35rem;
      border-radius: 5px;
      font-size: 0.83em;
    }}
    .md-content pre {{
      border: 1px solid var(--border);
      border-radius: 10px;
      background: var(--bg);
      padding: 0.8rem 0.9rem;
      overflow-x: auto;
      white-space: pre-wrap;
      word-break: break-word;
      line-height: 1.3;
    }}
    .md-content pre code {{
      background: transparent;
      border: 0;
      padding: 0;
      border-radius: 0;
      font-size: inherit;
      line-height: inherit;
    }}
    .gallery-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 0.75rem;
    }}
    .gallery-item {{
      margin: 0;
      background: var(--surface2);
      border: 1px solid var(--border);
      border-radius: 10px;
      overflow: hidden;
    }}
    .gallery-open {{
      display: block;
      width: 100%;
      border: 0;
      padding: 0;
      margin: 0;
      background: transparent;
      cursor: zoom-in;
    }}
    .gallery-item img {{
      display: block;
      width: 100%;
      height: 220px;
      object-fit: contain;
      background: #090b12;
    }}
    .gallery-item figcaption {{
      padding: 0.55rem 0.7rem 0.65rem;
      font-size: 0.78rem;
      color: var(--text2);
      line-height: 1.5;
    }}
    .turns {{
      display: grid;
      gap: 0.8rem;
    }}
    .turn-card {{
      border: 1px solid var(--border);
      border-left-width: 3px;
      border-radius: 10px;
      background: var(--surface2);
      padding: 0.75rem 0.85rem;
    }}
    .turn-user {{
      border-left-color: var(--accent);
    }}
    .turn-agent {{
      border-left-color: var(--highlight);
    }}
    .turn-other {{
      border-left-color: var(--text2);
    }}
    .turn-header {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 0.45rem;
      font-family: var(--font-code);
      font-size: 0.68rem;
      color: var(--text2);
      text-transform: uppercase;
      letter-spacing: 0.08em;
    }}
    .empty-note {{
      color: var(--text2);
      font-size: 0.84rem;
      margin: 0;
    }}
    .gallery-lightbox {{
      width: min(94vw, 980px);
      max-width: min(94vw, 980px);
      max-height: 92vh;
      border: 1px solid var(--border);
      border-radius: 12px;
      background: var(--surface);
      color: var(--text);
      padding: 0.8rem 0.8rem 0.6rem;
      position: fixed;
      inset: 50% auto auto 50%;
      transform: translate(-50%, -50%);
      margin: 0;
      overflow: auto;
    }}
    .gallery-lightbox::backdrop {{
      background: rgba(0, 0, 0, 0.75);
      backdrop-filter: blur(2px);
    }}
    .lightbox-close {{
      position: absolute;
      top: 0.45rem;
      right: 0.45rem;
      width: 2rem;
      height: 2rem;
      border-radius: 999px;
      border: 1px solid var(--border);
      background: var(--surface2);
      color: var(--text);
      font-size: 1.1rem;
      line-height: 1;
      cursor: pointer;
    }}
    .lightbox-img {{
      display: block;
      max-width: 100%;
      max-height: min(80vh, 860px);
      margin: 0 auto;
      border-radius: 8px;
      background: #090b12;
      object-fit: contain;
    }}
    .lightbox-caption {{
      margin-top: 0.55rem;
      font-size: 0.82rem;
      color: var(--text2);
      text-align: center;
      line-height: 1.5;
    }}
    @media (max-width: 680px) {{
      .polis-page {{
        padding-top: 1.25rem;
      }}
      .polis-card {{
        padding: 0.85rem;
      }}
      .meta-row {{
        flex-direction: column;
        align-items: flex-start;
        gap: 0.2rem;
      }}
    }}
  </style>
</head>
<body>
  <main class="container polis-page">
    <header class="polis-header">
      <a class="polis-back" href="{html.escape(home_href, quote=True)}">Back to The Polis</a>
      <h1>{html.escape(agent_name, quote=False)}</h1>
      <p class="polis-subtitle">Polis Showcase</p>
    </header>

    <section class="polis-grid">
      <article class="polis-card">
        <h2>Metadata</h2>
        <div class="meta-grid">
          <div class="meta-row"><span class="meta-key">Agent</span><span class="meta-value">{html.escape(agent_name, quote=False)}</span></div>
          <div class="meta-row"><span class="meta-key">Model</span><span class="meta-value">{html.escape(model_name, quote=False)}</span></div>
          <div class="meta-row"><span class="meta-key">Turns</span><span class="meta-value">{total_turns}</span></div>
          {submitter_html}
        </div>
      </article>

      <article class="polis-card">
        <h2>Agent Description</h2>
        <div class="md-content">{description_html or '<p class="empty-note">No agent description provided.</p>'}</div>
      </article>

      <article class="polis-card">
        <h2>Gallery</h2>
        {gallery_html}
      </article>

      <article class="polis-card">
        <h2>Genesis Snippet</h2>
        <pre class="polis-code"><code>{html.escape(genesis_snippet, quote=False)}</code></pre>
      </article>

      <article class="polis-card">
        <h2>Generated Agent REPL</h2>
        <pre class="polis-code"><code>{html.escape(generated_agent_repl or '# Unable to extract Python code from model_response.', quote=False)}</code></pre>
      </article>

      <article class="polis-card">
        <h2>Conversation ({total_turns} turns)</h2>
        <div class="turns">
          {turns_html}
        </div>
      </article>
    </section>
  </main>

  <dialog id="galleryLightbox" class="gallery-lightbox" aria-label="Image lightbox">
    <button type="button" class="lightbox-close" id="galleryLightboxClose" aria-label="Close image preview">×</button>
    <img id="galleryLightboxImage" class="lightbox-img" alt="">
    <p id="galleryLightboxCaption" class="lightbox-caption" hidden></p>
  </dialog>

  <script>
    (() => {{
      const dialog = document.getElementById('galleryLightbox');
      const image = document.getElementById('galleryLightboxImage');
      const caption = document.getElementById('galleryLightboxCaption');
      const closeBtn = document.getElementById('galleryLightboxClose');
      if (!dialog || !image || !caption || !closeBtn) return;

      const closeLightbox = () => {{
        if (dialog.open) dialog.close();
      }};

      for (const button of document.querySelectorAll('.gallery-open')) {{
        button.addEventListener('click', () => {{
          const src = button.getAttribute('data-src');
          if (!src) return;
          const cap = button.getAttribute('data-caption') || '';
          const alt = button.querySelector('img')?.getAttribute('alt') || '';
          image.src = src;
          image.alt = alt;
          caption.textContent = cap;
          caption.hidden = !cap;
          dialog.showModal();
        }});
      }}

      closeBtn.addEventListener('click', closeLightbox);
      dialog.addEventListener('click', (event) => {{
        const rect = dialog.getBoundingClientRect();
        const within = (
          event.clientX >= rect.left &&
          event.clientX <= rect.right &&
          event.clientY >= rect.top &&
          event.clientY <= rect.bottom
        );
        if (!within) closeLightbox();
      }});
      document.addEventListener('keydown', (event) => {{
        if (event.key === 'Escape') closeLightbox();
      }});
    }})();
  </script>

</body>
</html>
"""


def load_submission(path: Path) -> dict[str, Any]:
    raw = path.read_text(encoding="utf-8")
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("Top-level JSON object is required.")
    if "turns" not in data and isinstance(data.get("user_prompts"), list):
        data["turns"] = [{"type": "user", "content": str(prompt)} for prompt in data["user_prompts"]]
    return data


def select_cover_image(images: Any, agent_rel_dir: str) -> str | None:
    if not isinstance(images, list) or not images:
        return None

    for image in reversed(images):
        src = ""
        if isinstance(image, dict):
            src = str(image.get("src", "")).strip()
        elif isinstance(image, str):
            src = image.strip()
        if not src:
            continue
        return f"/polis/{agent_rel_dir}/images/{src}".replace("//", "/")
    return None


def build_polis_entry(data: dict[str, Any], submission_dir: Path, polis_root: Path) -> dict[str, Any]:
    rel_dir = submission_dir.relative_to(polis_root).as_posix()
    submitter = data.get("submitter")
    submitter = submitter if isinstance(submitter, dict) else {}
    turns = data.get("turns")
    turn_count = len(turns) if isinstance(turns, list) else 0

    entry: dict[str, Any] = {
        "agent_name": str(data.get("agent_name") or submission_dir.name),
        "twitter_handle": str(submitter.get("twitter_handle") or ""),
        "github_username": str(submitter.get("github_username") or ""),
        "model": extract_model_name(data),
        "turn_count": turn_count,
        "url": f"/polis/{rel_dir}/",
    }
    cover = select_cover_image(data.get("images"), rel_dir)
    if cover:
        entry["image"] = cover
    return entry


def write_polis_manifest(repo_root: Path, entries: list[dict[str, Any]]) -> Path:
    manifest_path = repo_root / "polis.js"
    payload = json.dumps(entries, ensure_ascii=False, indent=2)
    manifest_path.write_text(
        f"const POLIS_LIST = {payload};\nwindow.POLIS_LIST = POLIS_LIST;\n",
        encoding="utf-8",
    )
    return manifest_path


def generate_pages(repo_root: Path, polis_root: Path) -> tuple[list[Path], list[dict[str, Any]]]:
    written: list[Path] = []
    entries: list[dict[str, Any]] = []
    for afs_json_path in sorted(polis_root.rglob("afs.json")):
        submission_dir = afs_json_path.parent
        data = load_submission(afs_json_path)
        output = submission_dir / "index.html"
        output.write_text(render_page(data, submission_dir, repo_root), encoding="utf-8")
        written.append(output)
        entries.append(build_polis_entry(data, submission_dir, polis_root))
    entries.sort(key=lambda item: item.get("agent_name", "").lower())
    return written, entries


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate Polis showcase pages from afs.json files.")
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parent,
        help="Path to repository root (default: script directory).",
    )
    parser.add_argument(
        "--polis-dir",
        type=Path,
        default=Path("polis"),
        help="Path to polis directory, relative to repo root unless absolute.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = args.repo_root.resolve()
    polis_root = args.polis_dir if args.polis_dir.is_absolute() else (repo_root / args.polis_dir)
    polis_root = polis_root.resolve()

    if not polis_root.exists():
        print(f"error: polis directory not found: {polis_root}", file=sys.stderr)
        return 1

    written, entries = generate_pages(repo_root=repo_root, polis_root=polis_root)
    manifest_path = write_polis_manifest(repo_root=repo_root, entries=entries)
    if not written:
        print(f"No afs.json files found under {polis_root}")
        print(f"- Wrote empty polis manifest: {manifest_path}")
        return 0

    print(f"Generated {len(written)} page(s):")
    for page in written:
        print(f"- {page}")
    print(f"- {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

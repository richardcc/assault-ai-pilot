"""
PDF -> chunks -> GPT -> structured Markdown pipeline.

Pipeline steps:
1) Load PDFs from /pdfs (or custom --input-dir)
2) Split each PDF text into overlapping chunks
3) Send each chunk to GPT
4) Save structured Markdown output per PDF

Usage:
  python process_pdfs.py
  python process_pdfs.py --input-dir ../ --output-dir ../processed
  python process_pdfs.py --model gpt-4o-mini --max-chunks-per-file 20

Environment:
  OPENAI_API_KEY=<your key>
"""

from __future__ import annotations

import argparse
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

try:
    from pypdf import PdfReader
except Exception as exc:  # pragma: no cover
    raise SystemExit("Missing dependency 'pypdf'. Install with: pip install pypdf") from exc

try:
    from openai import OpenAI
except Exception as exc:  # pragma: no cover
    raise SystemExit("Missing dependency 'openai'. Install with: pip install openai") from exc


SYSTEM_PROMPT = """You transform technical text chunks into structured markdown.
Rules:
- Output valid markdown only.
- Keep factual alignment with source chunk.
- Do not invent references.
- Structure with these sections (in this order):
  1) ## Key Points
  2) ## Entities
  3) ## Rules / Constraints
  4) ## Open Questions
- Use concise bullets.
"""


@dataclass(frozen=True)
class Chunk:
    file_name: str
    chunk_index: int
    char_start: int
    char_end: int
    text: str


def _normalize_text(text: str) -> str:
    cleaned = text.replace("\r\n", "\n").replace("\r", "\n")
    while "\n\n\n" in cleaned:
        cleaned = cleaned.replace("\n\n\n", "\n\n")
    return cleaned.strip()


def extract_pdf_text(pdf_path: Path) -> str:
    reader = PdfReader(str(pdf_path))
    pages: list[str] = []
    for page in reader.pages:
        pages.append(page.extract_text() or "")
    return _normalize_text("\n\n".join(pages))


def chunk_text(text: str, chunk_size: int, chunk_overlap: int) -> Iterable[tuple[int, int, str]]:
    if chunk_size <= 0:
        raise ValueError("chunk_size must be > 0")
    if chunk_overlap < 0:
        raise ValueError("chunk_overlap must be >= 0")
    if chunk_overlap >= chunk_size:
        raise ValueError("chunk_overlap must be < chunk_size")
    if not text:
        return

    step = chunk_size - chunk_overlap
    start = 0
    n = len(text)
    while start < n:
        end = min(start + chunk_size, n)
        yield start, end, text[start:end]
        if end >= n:
            break
        start += step


def discover_pdfs(input_dir: Path, recursive: bool) -> list[Path]:
    pattern = "**/*.pdf" if recursive else "*.pdf"
    return sorted(p for p in input_dir.glob(pattern) if p.is_file())


def _request_chunk_markdown(client: OpenAI, model: str, chunk: Chunk, retries: int = 3) -> str:
    user_prompt = (
        f"File: {chunk.file_name}\n"
        f"Chunk index: {chunk.chunk_index}\n"
        f"Char range: {chunk.char_start}-{chunk.char_end}\n\n"
        "Source chunk:\n"
        "-----\n"
        f"{chunk.text}\n"
        "-----\n"
    )
    last_error = None
    for attempt in range(1, retries + 1):
        try:
            response = client.responses.create(
                model=model,
                input=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
            )
            text = getattr(response, "output_text", "") or ""
            return text.strip()
        except Exception as exc:  # pragma: no cover
            last_error = exc
            if attempt < retries:
                time.sleep(1.5 * attempt)
            else:
                break
    raise RuntimeError(f"GPT call failed for chunk {chunk.chunk_index} of {chunk.file_name}: {last_error}")


def _render_markdown_document(pdf_name: str, chunk_sections: list[tuple[Chunk, str]]) -> str:
    lines: list[str] = []
    lines.append(f"# Processed Notes: {pdf_name}")
    lines.append("")
    lines.append(f"Generated chunks: {len(chunk_sections)}")
    lines.append("")
    for chunk, md in chunk_sections:
        lines.append(f"## Chunk {chunk.chunk_index} ({chunk.char_start}-{chunk.char_end})")
        lines.append("")
        lines.append(md if md else "_No output from model._")
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def parse_args() -> argparse.Namespace:
    script_dir = Path(__file__).resolve().parent
    default_input = script_dir.parent
    default_output = script_dir.parent / "processed"

    parser = argparse.ArgumentParser(description="Process PDFs and generate structured markdown with GPT.")
    parser.add_argument("--input-dir", type=Path, default=default_input)
    parser.add_argument("--output-dir", type=Path, default=default_output)
    parser.add_argument("--chunk-size", type=int, default=2200)
    parser.add_argument("--chunk-overlap", type=int, default=250)
    parser.add_argument("--recursive", action="store_true")
    parser.add_argument("--model", type=str, default="gpt-4o-mini")
    parser.add_argument("--max-chunks-per-file", type=int, default=0, help="0 means all chunks")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise SystemExit("OPENAI_API_KEY is required.")

    input_dir: Path = args.input_dir
    output_dir: Path = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    pdf_paths = discover_pdfs(input_dir, recursive=bool(args.recursive))
    if not pdf_paths:
        print(f"No PDF files found in: {input_dir}")
        return

    client = OpenAI(api_key=api_key)
    manifest: list[dict] = []
    total_chunks = 0

    for pdf_path in pdf_paths:
        text = extract_pdf_text(pdf_path)
        chunks: list[Chunk] = []
        for idx, (start, end, piece) in enumerate(
            chunk_text(text, chunk_size=int(args.chunk_size), chunk_overlap=int(args.chunk_overlap))
        ):
            chunks.append(
                Chunk(
                    file_name=pdf_path.name,
                    chunk_index=idx,
                    char_start=start,
                    char_end=end,
                    text=piece,
                )
            )

        if args.max_chunks_per_file > 0:
            chunks = chunks[: int(args.max_chunks_per_file)]

        chunk_outputs: list[tuple[Chunk, str]] = []
        for chunk in chunks:
            md = _request_chunk_markdown(client=client, model=args.model, chunk=chunk)
            chunk_outputs.append((chunk, md))
            print(f"{pdf_path.name}: chunk {chunk.chunk_index} processed")

        file_stem = pdf_path.stem
        raw_txt = output_dir / f"{file_stem}.txt"
        chunks_json = output_dir / f"{file_stem}.chunks.json"
        out_md = output_dir / f"{file_stem}.md"

        raw_txt.write_text(text, encoding="utf-8")
        chunks_json.write_text(
            json.dumps(
                [
                    {
                        "file_name": c.file_name,
                        "chunk_index": c.chunk_index,
                        "char_start": c.char_start,
                        "char_end": c.char_end,
                        "text": c.text,
                        "markdown": md,
                    }
                    for c, md in chunk_outputs
                ],
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        out_md.write_text(_render_markdown_document(pdf_path.name, chunk_outputs), encoding="utf-8")

        total_chunks += len(chunk_outputs)
        manifest.append(
            {
                "file_name": pdf_path.name,
                "chunks": len(chunk_outputs),
                "raw_text_file": raw_txt.name,
                "chunks_json_file": chunks_json.name,
                "markdown_file": out_md.name,
            }
        )
        print(f"Finished {pdf_path.name}: {len(chunk_outputs)} chunks -> {out_md.name}")

    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "input_dir": str(input_dir),
                "output_dir": str(output_dir),
                "model": args.model,
                "num_files": len(pdf_paths),
                "num_chunks": total_chunks,
                "files": manifest,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print(f"Done. Files={len(pdf_paths)} Chunks={total_chunks}")
    print(f"Manifest: {manifest_path}")


if __name__ == "__main__":
    main()

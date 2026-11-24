# LearningDesk 2.0 — Knowledge Atlas

Your personal, local academic knowledge base. No website hosting, API key or separate OpenAI API billing is needed. The Codex CLI uses your signed-in ChatGPT account and its applicable usage limits for analysis.

## First launch (Mac)

1. Unzip or clone into a permanent folder, e.g. `~/Documents/LearningDesk2`. Keep this folder.
2. Open Terminal and enter `cd ~/Documents/LearningDesk2` (change the path if needed).
3. Run `bash setup.command`. Python 3 must be installed. This installs two document parsing libraries.
4. Run `bash "Start LearningDesk.command"` in Terminal. The local interface opens at http://127.0.0.1:8765. Keep its Terminal window open. macOS may block double-clicked downloaded scripts, so use Terminal.
5. Import a PDF, DOCX, Markdown or TXT file through the interface or drag files into the `inbox` directory.
6. Open a second Terminal in this folder and run `bash "Index with Codex.command"` or open Codex CLI and ask: **Index all pending learning materials according to AGENTS.md.** Sign in with ChatGPT (not an API key). Review any file write approvals Codex requests.
7. Refresh LearningDesk when indexing finishes.

## Three views

- **Knowledge Tree**: domains, modules, submodules, concepts. Expand/collapse, search ideas, and click a concept to view its references.
- **Connections**: zoomable, pannable graph. Click nodes for explanations or edges for the relationship and supporting evidence.
- **Library**: original documents, local import status, source downloads.

When you import a second textbook, Codex reads the existing catalog and integrates overlapping content, preserving each document's evidence. The application checks that quotes match the parsed source. It does not generate sample concepts or fabricate an atlas.

## Storage and limitations

`data/atlas.sqlite` stores extracted sections, concepts, placements, source references and connections. `data/originals/` contains untouched source files, deduplicated by file hash. Back up the whole folder (stop the server before making a manual copy). Do not delete or move this data directory independently of the project.

The server listens only on loopback; it is accessible to processes and users on the same computer, and has no separate login. It does not sync across devices. Python parsing happens locally; the AI analysis handled by Codex may send source excerpts to ChatGPT subject to your account's data settings. Only import materials you are permitted to process.

Text-bearing PDFs are supported; scanned or image-only PDFs need OCR first. DOCX paragraphs and tables are parsed, not embedded images. Source references use PDF pages, DOCX paragraph/table numbers, and text line ranges. Complex tables, equations and multi-column PDFs may require manual review.

Indexing is initiated by you through Codex, not a continuously running autonomous service. Large books may require several sessions due to model context or account limits; pending sections can be resumed. Deduplication and connections depend on the quality of Codex's analysis. Graph visualization can become crowded with very large collections. The local server itself makes no network calls.

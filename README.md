# tpf-archive

A custom static site generator for transforming a Plush Forums data export into a permanent, searchable, read-only archive of The Philosophy Forum.

This project powers https://archive.thephilosophyforum.com.

## Goals

- Preserve long-running forum discussions as a permanent archive
- Eliminate database and runtime dependencies
- Provide fast, full-text search over historical content
- Produce a deployable static site with minimal infrastructure

## Context

When [The Philosophy Forum (TPF)](https://thephilosophyforum.com) migrated from Plush Forums to Discourse, the historical
data was not migrated to the new platform.

- over a decade of philosophical discussion remains accessible
- user contributions are preserved in a stable, non-interactive form
- the archive can be hosted and maintained with minimal ongoing cost

The archive covers the Plush Forums era of TPF (October 2015 to January 2026).

## Structure

At a high level, the system works as follows:

Plush Forums JSON export
→ custom Python parsing and transformation
→ static HTML pages + search indexes
→ deployable archive site


All content is rendered ahead of time. The resulting site is fully static.

## Features

- Full-text search across discussions and comments
- User-based browsing and post histories
- Category-based navigation
- Search indexes generated at build time
- Static HTML output suitable for long-term hosting

## Building

```sh
python3 converter/convert_forum.py
npx pagefind --site build/static_archive --glob "discussions/*.html"
```

The first command generates the static site. The second builds the full-text search index using [Pagefind](https://pagefind.app), which crawls the rendered HTML and produces a chunked, on-demand index under `build/static_archive/pagefind/`. Both steps are required before deploying.

To deploy:

```sh
bash scripts/deploy.sh
```

## Search

The archive has two search modes:

- **Title & Author** — client-side search over discussion titles and authors using a pre-built JSON index, loaded on page load
- **Full Text** — full-text search over all discussion and comment content, powered by Pagefind; index chunks are loaded on demand per query

Phrase search is supported in the full-text mode: wrap terms in quotation marks (e.g. `"categorical imperative"`) for exact matches.

## Implementation notes

The generator is written in Python and operates entirely on exported forum data. Runtime performance is achieved through precomputation:

- search indexes are built during generation
- large datasets are chunked for client-side loading
- no database or server-side processing is required after deployment

This repository contains the tooling required to generate the archive; the generated site itself is treated as an output artefact.

## Status

This project is complete and maintained primarily for archival purposes. The focus is on stability, reproducibility, and long-term accessibility.

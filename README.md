# Khushu Quran Data

This repository contains static assets and catalogs for translations, recitations, word-by-word (WBW) segments, custom page fonts, and updates. It serves as a content delivery network (CDN) / file host for the **Osprey / Khushu** app.

## How to push to your GitHub

1. Create a new public repository on GitHub (e.g. `khushu-quran-data`).
2. Run the following commands in this directory:
   ```bash
   git remote add origin git@github.com:<YOUR_GITHUB_USERNAME>/<YOUR_REPO_NAME>.git
   git branch -M master
   git push -u origin master
   ```

## Directory Structure
- `inventory/translations/`: 48 translation books in 24 languages.
- `inventory/tafsirs/`: Tafsir availability indexes.
- `inventory/recitations/`: Reciters list and audio tracking indexes.
- `inventory/wbw/`: Word-by-word indexes.
- `inventory/fonts/`: Page-split font glyph files.

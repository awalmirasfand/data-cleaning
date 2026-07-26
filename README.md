# Data Cleaning App

A desktop GUI application for cleaning URL / domain data, removing duplicates, and classifying TLDs against accepted / rejected lists.

## Features

- **Dark / Light theme toggle** with modern CustomTkinter UI
- **Paste Excel columns** directly into the app, or **browse a `.xlsx` / `.csv` file**
- **Three sequential operations:**
  1. **Clean Data** — strips `http(s)://`, `www.`, paths, slashes, spaces; lowercases; normalizes domains via `tldextract`
  2. **Remove Duplicates** — drops duplicate rows by Column A (keeps first occurrence)
  3. **Check TLDs** — classifies each domain's TLD against your accepted / rejected lists
- **Workflow mode toggle:** "Chain" (operate on current state) or "Restart from Input" (always restart from raw loaded data)
- **TLD management window** to view / edit accepted & rejected TLD lists at any time
- **Bulk review window** when new TLDs are encountered — accept or reject each one in a single screen
- **TLD lists persist** between sessions (saved to `~/.data_cleaning_app/tld_config.json`)
- **Live data preview** (first 100 rows) with status bar showing row counts
- **Download to Excel** with smart sheet structure:
  - After Clean → single `Sheet1`
  - After Remove Duplicates → single `Cleaned`
  - After TLD Check → `Accepted` + `Rejected` + `TLD Config` sheets

## How to Use

1. Download `DataCleaningApp.exe` from the [Releases page](../../releases)
2. Run `DataCleaningApp.exe`
3. Paste your Excel columns into the input box (Column A = website URL), or click **Browse Excel / CSV...**
4. Click **Load Input Data**
5. Click the operation buttons in order (or any order — your choice based on the Mode toggle):
   - **1. Clean Data**
   - **2. Remove Duplicates**
   - **3. Check TLDs** (opens a bulk review window if new TLDs are found)
6. Click **Download Excel** to save the current state to a `.xlsx` file
7. Use **Manage TLDs** anytime to view / edit your accepted & rejected TLD lists

## Running from Source

```bash
pip install -r requirements.txt
python app.py
```

## Building the .exe

The `.exe` is built automatically by GitHub Actions (see `.github/workflows/build-release.yml`). To build locally:

```bash
pip install -r requirements.txt
pip install pyinstaller
pyinstaller --onefile --windowed --name DataCleaningApp app.py
```

The executable will be in `dist/DataCleaningApp.exe`.

## Input Format

Paste Excel columns (tab-separated, copied directly from Excel). Column A must be the website URL. The first row is treated as a header by default (toggleable via the "First row is header" checkbox).

| Column A (website url) | Column B | Column C | ... |
|------------------------|----------|----------|-----|
| https://www.example.com/path | name1 | note1 | ... |
| http://test.org/ | name2 | note2 | ... |

## TLD Configuration

- Accepted and rejected TLD lists are stored in `~/.data_cleaning_app/tld_config.json`
- The lists are auto-loaded when the app starts and auto-saved whenever you make changes
- Use the **Manage TLDs** button to manually edit the lists (one TLD per line, with or without the leading dot)

## Requirements

- `customtkinter>=5.2.0`
- `pandas>=2.0.0`
- `openpyxl>=3.1.0`
- `tldextract>=5.0.0`

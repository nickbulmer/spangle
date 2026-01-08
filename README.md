# spangle

Automatically generate eBay listings by analyzing product images with ChatGPT Vision.

## Features

- 📸 **Image Analysis**: Drop photos into local product folders, analyze with ChatGPT Vision
- 🤖 **AI-Powered**: ChatGPT generates titles, descriptions, pricing, and all listing details
- 📋 **Multiple Formats**: Saves listings as JSON and CSV for easy review
- 🚀 **Auto-Post**: Optional automatic posting to eBay (requires eBay API credentials)
- 📁 **Local-first**: Designed for Windows Google Drive sync (no Google Drive API required)

## Quick Start

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Create `.env` file with your credentials:
   ```
   OPENAI_API_KEY=your-key
   ```

3. Run:
   ```bash
   python ebay_automator.py
   ```

## Workflow

1. Take photos/video on iPhone
2. Put photos into `products/<product_folder>/` (your Google Drive sync will handle moving them to this PC)
3. Run script → ChatGPT analyzes images
4. Review generated listings
5. Optionally post to eBay automatically

## Documentation

See [SETUP.md](SETUP.md) for detailed setup instructions.

## eBay Account Manager (new)

This adds:
- Order syncing (so you can see what needs packing/shipping)
- Buyer message syncing + ChatGPT draft replies
- Packing workflow (enter packed weight/dimensions)
- DHL tier/price calculation + “collection request” payload generation

Run:

```bash
python ebay_manager.py
```

Configure `.env` with your eBay credentials (see `SETUP.md`).

## Folder-per-product listing generation (new)

If your Google Drive is synced locally (e.g. `D:\GoogleDrive\My Drive\projects\selling`), the easiest workflow is:

- Create `products/your_product_folder/`
- Drop photos into that folder
- Run:

```bash
python folder_automator.py
```

Outputs:
- `products/your_product_folder/listing.json`
- `listing_outputs/listings.csv`

## Turntable video support (new)

If you include a `.mov`/`.mp4` in the product folder, spangle will:
- Extract 3 frames (first/middle/last) into `products/<folder>/_derived/frames/`
- Create a first-3-seconds highlight clip at `products/<folder>/_derived/highlight_first3s.mp4`

Requires `ffmpeg` installed and on PATH.

## Requirements

- Python 3.8+
- OpenAI API key
- Google Drive API credentials
- (Optional) eBay API credentials for auto-posting

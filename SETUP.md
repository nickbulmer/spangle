# spangle - Setup Instructions

This tool generates eBay listings by analyzing product photos from your local filesystem (ideal for Windows Google Drive sync).

## Quick Start

1. **Install Dependencies**
   ```bash
   pip install -r requirements.txt
   ```

2. **Get OpenAI API Key**
   - Go to https://platform.openai.com/api-keys
   - Create a new API key
   - Copy the key

3. **Configure Environment Variables**
   - Create a file named `.env` in this folder
   - Fill in your credentials:
     ```
     OPENAI_API_KEY=your-openai-api-key-here
     ```

4. **Run the Script**
   ```bash
   python ebay_automator.py
   ```

## eBay Account Manager (orders, messages, packing, DHL)

Run:

```bash
python ebay_manager.py
```

Required `.env` variables:

```
EBAY_APP_ID=your-ebay-app-id
EBAY_DEV_ID=your-ebay-dev-id
EBAY_CERT_ID=your-ebay-cert-id
EBAY_TOKEN=your-ebay-user-token
EBAY_SITE_ID=3
```

### OpenAI usage & costs (local tracking)

spangle records OpenAI token usage to `ebay_data.db` whenever it calls the OpenAI API.  
To see a summary, run `python ebay_manager.py` and choose the menu option **OpenAI usage & cost (local estimate)**.

Pricing is a best-effort estimate; update `openai_costs.py` if you want accurate USD cost reporting.

Optional (for DHL collection payload defaults):

```
SENDER_NAME=Your Name
SENDER_PHONE=07123456789
SENDER_ADDRESS1=123 Street
SENDER_ADDRESS2=
SENDER_CITY=London
SENDER_POSTCODE=SW1A1AA
SENDER_COUNTRY=GB
```

## Folder-per-product workflow (recommended for Windows Google Drive sync)

Because your Google Drive is synced locally at `D:\GoogleDrive\My Drive\projects\selling`, you can skip the Drive API entirely and just use a local folder-per-product workflow.

### 1. Create a products folder

Create:

- `products/`
  - `your_product_1/` (put photos here)
  - `your_product_2/` (put photos here)

### 2. Run the local folder automator

```bash
python folder_automator.py
```

It will:
- Find each product subfolder under `products/`
- Send images to ChatGPT Vision
- Write `listing.json` inside that product folder
- Append a row to `listing_outputs/listings.csv`
- Create a `.processed` marker file so it won’t reprocess the folder

### Video support (turntable workflow)

If you drop a `.mov` or `.mp4` into a product folder, spangle can:
- Extract **3 key frames** (first/middle/last) for ChatGPT analysis
- Create a **first-3-seconds highlight clip** at `products/<folder>/_derived/highlight_first3s.mp4`

This requires `ffmpeg` + `ffprobe` available on your PATH.

Windows install options:
- `winget install Gyan.FFmpeg`
- or install from `https://ffmpeg.org/` and add it to PATH

### Optional: watch mode

If you want it to keep polling for new folders:

```
WATCH_PRODUCTS=true
WATCH_INTERVAL_SECONDS=10
```

### Optional: configure the products path

If you want `products/` somewhere else:

```
PRODUCTS_ROOT=D:\\GoogleDrive\\My Drive\\projects\\selling\\products
```

## Optional: eBay API Setup (for automatic listing)

If you want to automatically create listings on eBay:

1. **Get eBay API Credentials**
   - Go to https://developer.ebay.com/
   - Sign in and create a developer account
   - Create a new application
   - Get your credentials:
     - Application ID (App ID)
     - Developer ID (Dev ID)
     - Certificate ID (Cert ID)
     - User Token (requires OAuth flow)

2. **Add to .env file**
   ```
   EBAY_APP_ID=your-app-id
   EBAY_DEV_ID=your-dev-id
   EBAY_CERT_ID=your-cert-id
   EBAY_TOKEN=your-user-token
   AUTO_CREATE_LISTING=true
   ```

## Workflow

1. **Take Photos/Video**
   - Use your iPhone to take photos and video of the product
   - Capture multiple angles, any defects, labels, etc.

2. **Upload to Google Drive**
   - Upload images to your configured Google Drive folder
   - The script will download all images from this folder

3. **Run the Script**
   - The script will:
     - Download images from Google Drive
     - Analyze them with ChatGPT Vision
     - Generate complete listing details (title, description, condition, price, etc.)
     - Save results to `listing_outputs/` folder
     - Optionally create eBay listing automatically

4. **Review and Post**
   - Check the generated files in `listing_outputs/`
   - Review the JSON file for full details
   - All listings are also saved to `listing_outputs/listings.csv`
   - If `AUTO_CREATE_LISTING=true`, listings are posted automatically

## File Structure

```
project/
├── ebay_automator.py      # Main script
├── requirements.txt       # Python dependencies
├── credentials.json       # Google Drive API credentials (you create this)
├── token.json            # Auto-generated Google auth token
├── .env                  # Your API keys (you create this)
├── downloaded_images/    # Images downloaded from Drive
└── listing_outputs/      # Generated listing files
    ├── listings.csv      # All listings in CSV format
    └── listing_*.json    # Individual listing details
```

## Troubleshooting

### Google Drive Authentication
- First run will open a browser for authentication
- `token.json` will be created automatically
- If authentication fails, delete `token.json` and try again

### No Images Found
- Verify your Google Drive folder ID is correct
- Make sure images are in the folder (not subfolders)
- Check that images are not in Trash

### ChatGPT Errors
- Verify your OpenAI API key is correct
- Check your OpenAI account has credits
- Ensure images are valid image files

### eBay Listing Errors
- Verify all eBay credentials are correct
- Check that your eBay account is in good standing
- Ensure category IDs are valid for your eBay site

## Notes

- Images are downloaded to `downloaded_images/` folder
- The script processes all images in the folder at once
- For multiple products, use separate folders or run the script multiple times
- Video files are detected but not analyzed (OpenAI Vision doesn't support video yet)
- Review generated listings before posting to eBay

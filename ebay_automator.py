import os
import json
import csv
from pathlib import Path
from openai import OpenAI
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
import io
from ebaysdk.trading import Connection as Trading
from ebaysdk.exception import ConnectionError
import time
from datetime import datetime
import base64

class eBayListingAutomator:
    def __init__(self, openai_api_key, google_drive_folder_id=None, ebay_app_id=None, 
                 ebay_dev_id=None, ebay_cert_id=None, ebay_token=None):
        """
        Initialize the automator
        
        Args:
            openai_api_key: Your OpenAI API key
            google_drive_folder_id: Google Drive folder ID containing images
            ebay_*: eBay API credentials (optional if only generating listings)
        """
        self.openai_client = OpenAI(api_key=openai_api_key)
        self.drive_folder_id = google_drive_folder_id
        self.ebay_config = None
        
        if all([ebay_app_id, ebay_dev_id, ebay_cert_id, ebay_token]):
            self.ebay_config = {
                'appid': ebay_app_id,
                'devid': ebay_dev_id,
                'certid': ebay_cert_id,
                'token': ebay_token,
                'siteid': '0',  # US site
                'config_file': None
            }
        
        # Create directories for downloaded images and outputs
        self.images_dir = Path('downloaded_images')
        self.images_dir.mkdir(exist_ok=True)
        self.output_dir = Path('listing_outputs')
        self.output_dir.mkdir(exist_ok=True)
    
    def authenticate_google_drive(self):
        """Authenticate with Google Drive API"""
        SCOPES = ['https://www.googleapis.com/auth/drive.readonly']
        creds = None
        
        # Check for existing token
        if os.path.exists('token.json'):
            creds = Credentials.from_authorized_user_file('token.json', SCOPES)
        
        # If no valid credentials, get them
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                if not os.path.exists('credentials.json'):
                    raise FileNotFoundError(
                        "credentials.json not found. Please download it from Google Cloud Console. "
                        "See SETUP.md for instructions."
                    )
                flow = InstalledAppFlow.from_client_secrets_file(
                    'credentials.json', SCOPES)
                creds = flow.run_local_server(port=0)
            
            # Save credentials for next run
            with open('token.json', 'w') as token:
                token.write(creds.to_json())
        
        return build('drive', 'v3', credentials=creds)
    
    def download_images_from_drive(self, folder_id=None):
        """Download images from Google Drive folder"""
        if not folder_id:
            folder_id = self.drive_folder_id
        
        if not folder_id:
            print("No Google Drive folder ID provided")
            return []
        
        try:
            drive_service = self.authenticate_google_drive()
            
            # List all files in the folder
            query = f"'{folder_id}' in parents and trashed=false"
            results = drive_service.files().list(
                q=query,
                fields="files(id, name, mimeType)"
            ).execute()
            
            items = results.get('files', [])
            image_files = []
            
            # Filter for images and videos
            image_extensions = ['image/jpeg', 'image/png', 'image/gif', 'image/webp', 
                              'image/heic', 'image/heif', 'image/jpg']
            video_extensions = ['video/mp4', 'video/mov', 'video/quicktime']
            
            for item in items:
                mime_type = item.get('mimeType', '')
                if mime_type in image_extensions or mime_type in video_extensions:
                    file_id = item['id']
                    file_name = item['name']
                    
                    # Download the file
                    request = drive_service.files().get_media(fileId=file_id)
                    file_path = self.images_dir / file_name
                    
                    with io.FileIO(str(file_path), 'wb') as fh:
                        downloader = MediaIoBaseDownload(fh, request)
                        done = False
                        while done is False:
                            status, done = downloader.next_chunk()
                    
                    image_files.append(str(file_path))
                    print(f"Downloaded: {file_name}")
            
            return image_files
            
        except Exception as e:
            print(f"Error downloading from Google Drive: {e}")
            # Most common case in a Windows-synced Google Drive setup:
            # user wants local folder processing instead of Drive API OAuth.
            msg = str(e)
            if "credentials.json not found" in msg:
                print()
                print("Tip: If your Google Drive is synced locally (e.g. D:\\GoogleDrive\\My Drive\\...),")
                print("you don't need the Google Drive API. Use the local folder workflow instead:")
                print("  1) Create products\\<product_name>\\ and put photos inside")
                print("  2) Run: python folder_automator.py")
            return []
    
    def analyze_images_with_chatgpt(self, image_paths, video_path=None):
        """Use ChatGPT Vision to analyze images and generate listing details"""
        
        # Prepare image messages
        messages = [
            {
                "role": "system",
                "content": """You are an expert eBay listing writer. Analyze the provided images/video of a product and generate comprehensive listing details.

Return your analysis as JSON with these exact keys:
- name: Product name/title (max 80 chars for eBay)
- description: Detailed HTML-formatted description
- condition: One of: "New", "New with tags", "New without tags", "New with defects", "Used - Excellent", "Used - Very Good", "Used - Good", "Used - Acceptable", "For parts"
- category: eBay category name (e.g., "Electronics", "Clothing, Shoes & Accessories", "Home & Garden")
- price: Suggested starting price (number as string, e.g., "99.99")
- quantity: Number available (usually "1")
- shipping_cost: Estimated shipping cost (number as string, e.g., "10.00")
- selling_points: Array of 3-5 key selling points
- keywords: Array of relevant search keywords
- brand: Brand name if identifiable
- model: Model number if identifiable
- dimensions: Dimensions if visible
- weight: Weight if visible/estimable
- notes: Any additional notes about condition, flaws, or special features"""
            }
        ]
        
        # Build content array with text and images
        content = [
            {
                "type": "text",
                "text": """Please analyze these product images/video and create a comprehensive eBay listing.

Consider:
- What the product is
- Its condition and any visible wear/defects
- Brand, model, or identifying features
- Appropriate category and pricing
- Compelling selling points
- SEO-optimized title and description

Return ONLY valid JSON matching the specified format."""
            }
        ]
        
        # Add images
        for img_path in image_paths:
            if os.path.exists(img_path):
                try:
                    with open(img_path, "rb") as image_file:
                        base64_image = base64.b64encode(image_file.read()).decode('utf-8')
                        mime_type = "image/jpeg"
                        if img_path.lower().endswith('.png'):
                            mime_type = "image/png"
                        elif img_path.lower().endswith('.gif'):
                            mime_type = "image/gif"
                        elif img_path.lower().endswith('.webp'):
                            mime_type = "image/webp"
                        elif img_path.lower().endswith(('.heic', '.heif')):
                            mime_type = "image/heic"
                        
                        content.append({
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{mime_type};base64,{base64_image}"
                            }
                        })
                except Exception as e:
                    print(f"Warning: Could not process image {img_path}: {e}")
        
        # Add video if provided
        if video_path and os.path.exists(video_path):
            # Note: OpenAI Vision API doesn't support video directly
            # You may need to extract frames or use a different approach
            content.append({
                "type": "text",
                "text": f"Note: A video file is also available at {video_path} but cannot be analyzed directly. Please use the images provided."
            })
        
        messages.append({
            "role": "user",
            "content": content
        })
        
        try:
            # Try gpt-4o first (if available), fallback to gpt-4-vision-preview
            try:
                response = self.openai_client.chat.completions.create(
                    model="gpt-4o",
                    messages=messages,
                    max_tokens=2000,
                    response_format={"type": "json_object"}
                )
            except:
                response = self.openai_client.chat.completions.create(
                    model="gpt-4-vision-preview",
                    messages=messages,
                    max_tokens=2000,
                    response_format={"type": "json_object"}
                )
            
            result = json.loads(response.choices[0].message.content)
            return result
            
        except Exception as e:
            print(f"Error analyzing images with ChatGPT: {e}")
            return None
    
    def save_listing_details(self, listing_data, output_file=None):
        """Save listing details to JSON and CSV files"""
        if not output_file:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_file = f"listing_{timestamp}"
        
        # Save as JSON
        json_path = self.output_dir / f"{output_file}.json"
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(listing_data, f, indent=2, ensure_ascii=False)
        print(f"Saved listing details to {json_path}")
        
        # Save/append to CSV
        csv_path = self.output_dir / "listings.csv"
        csv_exists = csv_path.exists()
        
        with open(csv_path, 'a', newline='', encoding='utf-8') as f:
            fieldnames = ['name', 'description', 'condition', 'category', 'price', 
                         'quantity', 'shipping_cost', 'brand', 'model', 'keywords']
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            
            if not csv_exists:
                writer.writeheader()
            
            # Flatten selling_points and keywords for CSV
            row = {
                'name': listing_data.get('name', ''),
                'description': listing_data.get('description', '').replace('\n', ' ')[:500],  # Truncate for CSV
                'condition': listing_data.get('condition', ''),
                'category': listing_data.get('category', ''),
                'price': listing_data.get('price', ''),
                'quantity': listing_data.get('quantity', '1'),
                'shipping_cost': listing_data.get('shipping_cost', ''),
                'brand': listing_data.get('brand', ''),
                'model': listing_data.get('model', ''),
                'keywords': ', '.join(listing_data.get('keywords', []))
            }
            writer.writerow(row)
        
        print(f"Added to CSV: {csv_path}")
        return json_path, csv_path
    
    def create_ebay_listing(self, listing_data, image_paths=None):
        """Create an eBay listing from the generated data"""
        if not self.ebay_config:
            print("eBay credentials not configured. Skipping listing creation.")
            return None
        
        try:
            api = Trading(config_file=None, **self.ebay_config)
            
            # Map condition
            condition_map = {
                'new': '1000',
                'new with tags': '1500',
                'new without tags': '1750',
                'new with defects': '2000',
                'used - excellent': '3000',
                'used - very good': '4000',
                'used - good': '5000',
                'used - acceptable': '6000',
                'for parts': '7000'
            }
            
            condition_lower = listing_data.get('condition', 'Used - Good').lower()
            condition_id = '5000'  # Default
            for key, code in condition_map.items():
                if key in condition_lower:
                    condition_id = code
                    break
            
            # Build description with selling points
            description = listing_data.get('description', '')
            selling_points = listing_data.get('selling_points', [])
            if selling_points:
                points_html = '<ul>' + ''.join([f'<li>{point}</li>' for point in selling_points]) + '</ul>'
                description = f"{description}\n\n<h3>Key Features:</h3>\n{points_html}"
            
            # Add notes if available
            if listing_data.get('notes'):
                description += f"\n\n<p><strong>Additional Notes:</strong> {listing_data.get('notes')}</p>"
            
            # Prepare request
            request = {
                'Item': {
                    'Title': listing_data.get('name', 'Item')[:80],  # eBay 80 char limit
                    'Description': description,
                    'PrimaryCategory': {
                        'CategoryID': self.get_category_id(listing_data.get('category', ''))
                    },
                    'StartPrice': listing_data.get('price', '0.00'),
                    'Quantity': listing_data.get('quantity', '1'),
                    'ConditionID': condition_id,
                    'ListingDuration': 'GTC',
                    'ListingType': 'FixedPriceItem',
                    'Country': 'US',
                    'Currency': 'USD',
                    'ShippingDetails': {
                        'ShippingServiceOptions': {
                            'ShippingServicePriority': '1',
                            'ShippingService': 'USPSPriority',
                            'ShippingServiceCost': listing_data.get('shipping_cost', '0.00'),
                            'ShippingServiceAdditionalCost': '0.00'
                        }
                    },
                    'ReturnPolicy': {
                        'ReturnsAcceptedOption': 'ReturnsAccepted',
                        'RefundOption': 'MoneyBack',
                        'ReturnsWithinOption': 'Days_30',
                        'ShippingCostPaidByOption': 'Buyer'
                    },
                    'PaymentMethods': 'PayPal'
                }
            }
            
            # Note: Adding pictures requires uploading to eBay's picture service first
            # This is a simplified version - you'll need to implement picture upload
            
            response = api.execute('AddItem', request)
            
            if response.reply.Ack == 'Success':
                item_id = response.reply.ItemID
                print(f"✓ Successfully listed on eBay!")
                print(f"  Item ID: {item_id}")
                print(f"  URL: https://www.ebay.com/itm/{item_id}")
                return item_id
            else:
                print(f"✗ Failed to create listing: {response.reply.Errors}")
                return None
                
        except ConnectionError as e:
            print(f"eBay API Error: {e}")
            return None
    
    def get_category_id(self, category_name):
        """Get eBay category ID from category name"""
        category_map = {
            'Cameras & Photo': '625',
            'Electronics': '58058',
            'Clothing, Shoes & Accessories': '11450',
            'Home & Garden': '11700',
            'Toys & Hobbies': '220',
            'Books': '267',
            'Collectibles': '1',
            'Jewelry & Watches': '281',
            'Sporting Goods': '888',
            'Musical Instruments': '619',
            'Art': '550',
            'Antiques': '20081',
            'Computers/Tablets & Networking': '58058',
            'Cell Phones & Accessories': '15032',
            'Video Games & Consoles': '1249'
        }
        return category_map.get(category_name, '1')
    
    def process_folder(self, drive_folder_id=None, create_listing=False):
        """Main workflow: Download images, analyze with ChatGPT, save details, optionally list"""
        print("=" * 60)
        print("eBay Listing Automator - Image Analysis Workflow")
        print("=" * 60)
        
        # Step 1: Download images from Google Drive
        print("\n[Step 1] Downloading images from Google Drive...")
        image_paths = self.download_images_from_drive(drive_folder_id)
        
        if not image_paths:
            print("No images found. Please check your Google Drive folder ID.")
            return None
        
        print(f"Downloaded {len(image_paths)} image(s)")
        
        # Step 2: Analyze with ChatGPT
        print("\n[Step 2] Analyzing images with ChatGPT Vision...")
        listing_data = self.analyze_images_with_chatgpt(image_paths)
        
        if not listing_data:
            print("Failed to generate listing details")
            return None
        
        print("✓ Analysis complete!")
        print(f"  Product: {listing_data.get('name', 'Unknown')}")
        print(f"  Condition: {listing_data.get('condition', 'Unknown')}")
        print(f"  Suggested Price: ${listing_data.get('price', '0.00')}")
        
        # Step 3: Save listing details
        print("\n[Step 3] Saving listing details...")
        json_path, csv_path = self.save_listing_details(listing_data)
        
        # Step 4: Create eBay listing (if requested)
        if create_listing:
            print("\n[Step 4] Creating eBay listing...")
            item_id = self.create_ebay_listing(listing_data, image_paths)
            if item_id:
                listing_data['ebay_item_id'] = item_id
                # Update JSON with item ID
                with open(json_path, 'w', encoding='utf-8') as f:
                    json.dump(listing_data, f, indent=2, ensure_ascii=False)
        else:
            print("\n[Step 4] Skipping eBay listing creation (set create_listing=True to enable)")
            print("  Review the generated files and run create_listing() separately if needed")
        
        print("\n" + "=" * 60)
        print("Workflow complete!")
        print("=" * 60)
        
        return listing_data


def main():
    """Main function - configure your settings here"""
    import os
    from dotenv import load_dotenv
    
    # Load environment variables from .env file
    load_dotenv()
    
    # Get credentials from environment variables or set directly
    OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
    GOOGLE_DRIVE_FOLDER_ID = os.getenv('GOOGLE_DRIVE_FOLDER_ID')
    
    if not OPENAI_API_KEY:
        print("Error: OPENAI_API_KEY not found in environment variables or .env file")
        print("Please set it in .env file or as an environment variable")
        return
    
    if not GOOGLE_DRIVE_FOLDER_ID:
        print("Error: GOOGLE_DRIVE_FOLDER_ID not found in environment variables or .env file")
        print("Please set it in .env file or as an environment variable")
        return
    
    # Optional: eBay credentials (only needed if creating listings)
    EBAY_APP_ID = os.getenv('EBAY_APP_ID')
    EBAY_DEV_ID = os.getenv('EBAY_DEV_ID')
    EBAY_CERT_ID = os.getenv('EBAY_CERT_ID')
    EBAY_TOKEN = os.getenv('EBAY_TOKEN')
    
    automator = eBayListingAutomator(
        openai_api_key=OPENAI_API_KEY,
        google_drive_folder_id=GOOGLE_DRIVE_FOLDER_ID,
        ebay_app_id=EBAY_APP_ID,
        ebay_dev_id=EBAY_DEV_ID,
        ebay_cert_id=EBAY_CERT_ID,
        ebay_token=EBAY_TOKEN
    )
    
    # Process the folder
    # Set create_listing=True to automatically create eBay listings
    create_listing = os.getenv('AUTO_CREATE_LISTING', 'False').lower() == 'true'
    
    automator.process_folder(
        drive_folder_id=GOOGLE_DRIVE_FOLDER_ID,
        create_listing=create_listing
    )


if __name__ == '__main__':
    main()

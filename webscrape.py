import requests
from bs4 import BeautifulSoup
import re
import os
import csv
from urllib.parse import urljoin, urlparse
import time
from collections import Counter

def scrape_page(url):
    """Scrape a single page and extract p tags and li tags in order"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Default classes to exclude if none provided
        exclude_classes = ['main-nav']
        
        # Remove unwanted elements completely before scraping
        for class_name in exclude_classes:
            for element in soup.find_all(class_=class_name):
                element.decompose() 

        # All the gabba goo
        elements = []
        for element in soup.find_all(['p', 'li', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'h7']):
            text = element.get_text(separator=' ', strip=True)
            if text:
                elements.append(text)
        
        return elements
        
    except Exception as e:
        print(f"Error scraping {url}: {e}")
        return None

def download_file(file_url, output_dir):
    """Download a file (PDF, DOCX, etc.) and save it to the output directory"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        # Determine file type for display
        file_type = "PDF" if file_url.lower().endswith('.pdf') or 'pdf' in file_url.lower() else "DOCX"
        print(f"Downloading {file_type}: {file_url}")
        
        response = requests.get(file_url, headers=headers, timeout=30)
        response.raise_for_status()
        
        # Generate filename from URL
        filename = file_url_to_filename(file_url)
        filepath = os.path.join(output_dir, filename)
        
        # Save the file
        with open(filepath, 'wb') as f:
            f.write(response.content)
        
        print(f"✓ {file_type} saved: {filename}")
        return True
        
    except Exception as e:
        print(f"✗ Error downloading file {file_url}: {e}")
        return False

def file_url_to_filename(file_url):
    """Convert file URL to valid filename, preserving original name when possible"""
    # Extract filename from URL
    parsed_url = urlparse(file_url)
    original_filename = os.path.basename(parsed_url.path)
    
    # If we have a proper file extension, clean it and use it
    if (original_filename.lower().endswith('.pdf') or 
        original_filename.lower().endswith('.docx') or
        original_filename.lower().endswith('.doc')):
        # Clean the filename
        filename = re.sub(r'[<>:"/\\|?*]', '_', original_filename)
        filename = re.sub(r'_+', '_', filename)
        filename = filename.strip('._')
    else:
        # Generate filename from full URL if no proper filename found
        filename = file_url.replace('https://', '').replace('http://', '')
        filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
        filename = re.sub(r'_+', '_', filename)
        filename = filename.rstrip('._')
        
        # Add appropriate extension based on URL content
        if 'pdf' in file_url.lower() and not filename.lower().endswith('.pdf'):
            filename += '.pdf'
        elif ('docx' in file_url.lower() or 'doc' in file_url.lower()) and not filename.lower().endswith(('.docx', '.doc')):
            filename += '.docx'
    
    return filename

def find_and_download_files(url, output_dir, downloaded_files):
    """Find all PDF and DOCX links on a page and download them"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        file_count = 0
        
        # Find all links
        for link in soup.find_all('a', href=True):
            href = link['href']
            full_url = urljoin(url, href)
            link_text = link.get_text().lower().strip()
            
            # Check if this is a PDF or DOCX link
            is_pdf = (full_url.lower().endswith('.pdf') or 
                     'pdf' in full_url.lower() or
                     link_text.endswith('.pdf'))
            
            is_docx = (full_url.lower().endswith(('.docx', '.doc')) or 
                      'docx' in full_url.lower() or 
                      'doc' in full_url.lower() or
                      link_text.endswith(('.docx', '.doc')))
            
            if (is_pdf or is_docx) and full_url not in downloaded_files:
                if download_file(full_url, output_dir):
                    downloaded_files.add(full_url)
                    file_count += 1
                    # Save file URL to CSV
                    csv_dir = 'backend'
                    save_file_to_csv(full_url, os.path.join(csv_dir, "discovered_files.csv"))
                    time.sleep(0.5)  # Be respectful with file downloads
        
        return file_count
        
    except Exception as e:
        print(f"Error finding files on {url}: {e}")
        return 0

def save_file_to_csv(file_url, csv_filepath):
    """Save file URL to CSV file"""
    file_exists = os.path.isfile(csv_filepath)
    
    with open(csv_filepath, 'a', newline='', encoding='utf-8') as csvfile:
        writer = csv.writer(csvfile)
        
        if not file_exists:
            writer.writerow(['url', 'type', 'file_name'])
        
        # Determine file type
        file_type = "PDF" if (file_url.lower().endswith('.pdf') or 'pdf' in file_url.lower()) else "DOCX"
        
        # Get the filename using the existing function
        filename = file_url_to_filename(file_url)
        
        writer.writerow([file_url, file_type, filename])

def identify_common_content(all_scraped_content, threshold=0.5):
    """Identify content that appears across multiple pages (likely header/footer)"""
    if len(all_scraped_content) < 2:
        return set()
    
    # Count occurrences of each paragraph across all pages
    text_counter = Counter()
    total_pages = len(all_scraped_content)
    
    for page_content in all_scraped_content:
        if page_content:
            unique_texts = set(page_content)  # Remove duplicates within same page
            for text in unique_texts:
                # Only consider substantial text (not single words or very short phrases)
                if len(text.strip()) > 15:  # Slightly higher threshold for paragraphs
                    text_counter[text.strip()] += 1
    
    # Identify text that appears on more than threshold percentage of pages
    common_threshold = max(2, int(total_pages * threshold))
    common_content = {text for text, count in text_counter.items() if count >= common_threshold}
    
    return common_content

def clean_content(p_contents, common_content=None):
    """Clean and format the paragraph content, removing common header/footer elements"""
    if not p_contents:
        return ""
    
    filtered_paragraphs = []
    
    for paragraph in p_contents:
        paragraph = paragraph.strip()
        
        # Skip empty paragraphs
        if not paragraph:
            continue
            
        # Skip common repetitive content if provided
        if common_content and paragraph in common_content:
            continue
            
        # Skip very short paragraphs that are likely navigation
        if len(paragraph) < 10:
            continue
            
            
        filtered_paragraphs.append(paragraph)
    
    # Join paragraphs with double newlines to maintain paragraph structure
    content = "\n\n".join(filtered_paragraphs)
    
    # Clean up excessive whitespace
    content = re.sub(r'\n{3,}', '\n\n', content)
    
    return content

def clean_text(text):
    """Clean and normalize text content"""
    if not text:
        return ""
    
    # Remove excessive whitespace
    text = re.sub(r'\s+', ' ', text)
    
    # Remove common unwanted patterns
    text = re.sub(r'^\s*[\|\-\*\•]\s*', '', text)  # Remove bullet points
    text = re.sub(r'\s*\n\s*', ' ', text)  # Replace newlines with spaces
    
    return text.strip()

def two_pass_scraping(base_url):
    """Two-pass approach: First pass identifies common content, second pass filters it out"""
    output_dir = "earlham_iowa_data"
    csv_dir = 'backend'
    csv_filepath = os.path.join(csv_dir, "discovered_files.csv")
    
    os.makedirs(output_dir, exist_ok=True)
    
    # Track downloaded files to avoid duplicates
    downloaded_files = set()
    total_files_downloaded = 0
    
    # PASS 1: Discover all URLs and scrape content for analysis
    print("Pass 1: Discovering pages and analyzing common content...")
    
    to_visit = {base_url}
    visited = set()
    all_scraped_content = []
    url_content_map = {}
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    base_domain = urlparse(base_url).netloc
    
    while to_visit and len(visited):  # Limit for analysis phase
        current_url = to_visit.pop()
        
        if current_url in visited:
            continue
            
        visited.add(current_url)
        print(f"Analyzing page {len(visited)}: {current_url}")
        
        try:
            # Check for and download files on this page
            file_count = find_and_download_files(current_url, output_dir, downloaded_files)
            total_files_downloaded += file_count
            
            # Scrape p tag content
            p_contents = scrape_page(current_url)
            if p_contents:
                all_scraped_content.append(p_contents)
                url_content_map[current_url] = p_contents
                
                # Save content immediately (without filtering for now)
                raw_content = clean_content(p_contents, common_content=None)
                save_page_content(current_url, raw_content, output_dir, csv_filepath)
            
            # Discover new links
            response = requests.get(current_url, headers=headers, timeout=10)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')
            
            for link in soup.find_all('a', href=True):
                href = link['href']
                full_url = urljoin(current_url, href)
                parsed_url = urlparse(full_url)
                clean_url = f"{parsed_url.scheme}://{parsed_url.netloc}{parsed_url.path}"
                
                # Only add HTML pages to visit queue, not files
                if (parsed_url.netloc == base_domain and 
                    clean_url.startswith(base_url) and 
                    clean_url not in visited and
                    clean_url not in to_visit and
                    not clean_url.lower().endswith(('.pdf', '.docx', '.doc'))):
                    to_visit.add(clean_url)
            
            time.sleep(0.5)
            
        except Exception as e:
            print(f"Error in pass 1 for {current_url}: {e}")
    
    # Identify common content across pages
    print("\nIdentifying common header/footer paragraphs...")
    common_content = identify_common_content(all_scraped_content, threshold=0.4)
    print(f"Found {len(common_content)} common paragraphs to filter out")
    
    # PASS 2: Continue scraping with filtering
    print("\nPass 2: Scraping remaining pages with content filtering...")
    
    scraped_count = len(url_content_map)  # Count pages already saved in pass 1
    failed_count = 0
    
    # Re-process already scraped pages with better filtering (overwrite files)
    print("Re-processing Pass 1 pages with improved filtering...")
    for url, p_contents in url_content_map.items():
        cleaned_content = clean_content(p_contents, common_content)
        # Overwrite the files with better filtered content
        filename = url_to_filename(url)
        filepath = os.path.join(output_dir, filename)
        
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(f"# {url}\n\n")
            f.write(cleaned_content)
        print(f"✓ Re-processed: {filename}")
    
    # Continue with remaining pages
    while to_visit:
        current_url = to_visit.pop()
        
        if current_url in visited:
            continue
            
        visited.add(current_url)
        print(f"Processing page {len(visited)}: {current_url}")
        
        try:
            # Check for and download files on this page
            file_count = find_and_download_files(current_url, output_dir, downloaded_files)
            total_files_downloaded += file_count
            
            p_contents = scrape_page(current_url)
            if p_contents:
                # Save content immediately with filtering
                cleaned_content = clean_content(p_contents, common_content)
                if save_page_content(current_url, cleaned_content, output_dir, csv_filepath):
                    scraped_count += 1
                else:
                    failed_count += 1
            
            # Continue discovering links
            response = requests.get(current_url, headers=headers, timeout=10)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')
            
            for link in soup.find_all('a', href=True):
                href = link['href']
                full_url = urljoin(current_url, href)
                parsed_url = urlparse(full_url)
                clean_url = f"{parsed_url.scheme}://{parsed_url.netloc}{parsed_url.path}"
                
                # Only add HTML pages to visit queue, not files
                if (parsed_url.netloc == base_domain and 
                    clean_url.startswith(base_url) and 
                    clean_url not in visited and
                    clean_url not in to_visit and
                    not clean_url.lower().endswith(('.pdf', '.docx', '.doc'))):
                    to_visit.add(clean_url)
            
            time.sleep(0.5)
            
        except Exception as e:
            print(f"Error processing {current_url}: {e}")
            failed_count += 1
    
    print(f"\n{'='*50}")
    print(f"Scraping complete!")
    print(f"Successfully scraped: {scraped_count} pages")
    print(f"Failed to scrape: {failed_count} pages")
    print(f"Total pages discovered: {len(visited)}")
    print(f"Files downloaded: {total_files_downloaded}")
    print(f"Content saved to: {output_dir}/")

def save_page_content(url, content, output_dir, csv_filepath):
    """Save page content and URL"""
    if content and content.strip():
        filename = url_to_filename(url)
        filepath = os.path.join(output_dir, filename)
        
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(f"# {url}\n\n")
            f.write(content)
        
        # Save URL to CSV
        save_url_to_csv(url, csv_filepath)
        
        print(f"✓ Saved: {filename}")
        return True
    else:
        print(f"✗ No content to save: {url}")
        return False

def url_to_filename(url):
    """Convert URL to valid filename"""
    filename = url.replace('https://', '').replace('http://', '')
    filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
    filename = re.sub(r'_+', '_', filename)
    filename = filename.rstrip('._')
    return filename + '.md'

def save_url_to_csv(url, csv_filepath):
    """Save URL to CSV file"""
    file_exists = os.path.isfile(csv_filepath)
    
    with open(csv_filepath, 'a', newline='', encoding='utf-8') as csvfile:
        writer = csv.writer(csvfile)
        
        if not file_exists:
            writer.writerow(['url', 'type', 'file_name'])
        
        # Generate filename for the webpage
        filename = url_to_filename(url)
        
        writer.writerow([url, 'webpage', filename])

if __name__ == "__main__":
    base_url = "https://earlhamiowa.org/"
    two_pass_scraping(base_url)
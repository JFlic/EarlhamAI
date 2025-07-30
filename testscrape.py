import requests
from bs4 import BeautifulSoup
import re

def scrape_page_enhanced(url, include_nav=False):
    """
    Enhanced web scraper that extracts various text elements while filtering out unwanted content
    
    Args:
        url (str): URL to scrape
        include_nav (bool): Whether to include navigation content (default: False)
    
    Returns:
        dict: Dictionary containing different types of extracted content
    """
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Remove unwanted elements (navigation, ads, etc.) if not including nav
        if not include_nav:
            unwanted_selectors = [
                'nav', 'header', 'footer', 
                '.nav', '.navbar', '.navigation', '.menu',
                '.sidebar', '.ads', '.advertisement', '.social-media',
                '.breadcrumb', '.pagination', '.comments',
                '[class*="nav"]', '[id*="nav"]',
                '[class*="menu"]', '[id*="menu"]',
                '[class*="sidebar"]', '[id*="sidebar"]',
                '[class*="ad"]', '[id*="ad"]'
            ]
            
            for selector in unwanted_selectors:
                for element in soup.select(selector):
                    element.decompose()  # Remove element completely
        
        # Initialize results dictionary
        results = {
            'paragraphs': [],
            'headings': [],
            'lists': [],
            'divs': [],
            'spans': [],
            'tables': [],
            'blockquotes': [],
            'all_text': []
        }
        
        # Extract paragraphs
        for p in soup.find_all('p'):
            text = clean_text(p.get_text(separator=' ', strip=True))
            if text and len(text) > 10:  # Filter out very short paragraphs
                results['paragraphs'].append(text)
        
        # Extract headings (h1-h6)
        for i in range(1, 7):
            for h in soup.find_all(f'h{i}'):
                text = clean_text(h.get_text(strip=True))
                if text:
                    results['headings'].append({
                        'level': i,
                        'text': text
                    })
        
        # Extract lists (both ul and ol)
        for list_tag in soup.find_all(['ul', 'ol']):
            list_items = []
            for li in list_tag.find_all('li', recursive=False):  # Only direct children
                text = clean_text(li.get_text(separator=' ', strip=True))
                if text:
                    list_items.append(text)
            
            if list_items:
                results['lists'].append({
                    'type': list_tag.name,
                    'items': list_items
                })
        
        # Extract meaningful div content
        for div in soup.find_all('div'):
            # Skip divs that are likely containers or have minimal content
            if should_skip_container(div):
                continue
                
            # Get direct text content (not from nested elements)
            direct_text = get_direct_text(div)
            if direct_text and len(direct_text) > 20:
                results['divs'].append(direct_text)
        
        # Extract spans with substantial content
        for span in soup.find_all('span'):
            text = clean_text(span.get_text(strip=True))
            if text and len(text) > 15 and not is_likely_ui_element(span):
                results['spans'].append(text)
        
        # Extract tables
        for table in soup.find_all('table'):
            table_data = extract_table_data(table)
            if table_data:
                results['tables'].append(table_data)
        
        # Extract blockquotes
        for quote in soup.find_all('blockquote'):
            text = clean_text(quote.get_text(separator=' ', strip=True))
            if text:
                results['blockquotes'].append(text)
        
        # Extract all meaningful text as fallback
        # Remove script and style elements
        for script in soup(["script", "style"]):
            script.decompose()
        
        body_text = soup.get_text(separator=' ', strip=True)
        cleaned_text = clean_text(body_text)
        if cleaned_text:
            results['all_text'] = [cleaned_text]
        
        return results
        
    except Exception as e:
        print(f"Error scraping {url}: {e}")
        return None

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

def should_skip_container(element):
    """Determine if a div should be skipped (likely a container)"""
    # Skip if it has many child elements (likely a container)
    if len(element.find_all()) > 10:
        return True
    
    # Skip if it has certain classes/ids
    skip_patterns = ['container', 'wrapper', 'layout', 'grid', 'row', 'col']
    class_id = ' '.join(element.get('class', []) + [element.get('id', '')])
    
    return any(pattern in class_id.lower() for pattern in skip_patterns)

def get_direct_text(element):
    """Get only the direct text content of an element, not from nested elements"""
    direct_text = ""
    for content in element.contents:
        if hasattr(content, 'strip'):  # It's a text node
            direct_text += content.strip() + " "
    
    return clean_text(direct_text)

def is_likely_ui_element(element):
    """Check if a span is likely a UI element rather than content"""
    ui_patterns = ['icon', 'button', 'label', 'tag', 'badge', 'arrow']
    class_id = ' '.join(element.get('class', []) + [element.get('id', '')])
    
    return any(pattern in class_id.lower() for pattern in ui_patterns)

def extract_table_data(table):
    """Extract structured data from a table"""
    rows = []
    
    # Try to find headers
    headers = []
    header_row = table.find('tr')
    if header_row:
        for th in header_row.find_all(['th', 'td']):
            headers.append(clean_text(th.get_text(strip=True)))
    
    # Extract all rows
    for tr in table.find_all('tr')[1:]:  # Skip header row
        row_data = []
        for td in tr.find_all(['td', 'th']):
            row_data.append(clean_text(td.get_text(strip=True)))
        
        if row_data and any(cell for cell in row_data):  # Skip empty rows
            rows.append(row_data)
    
    return {
        'headers': headers,
        'rows': rows
    } if rows else None

# Example usage functions
def scrape_specific_content(url, content_types=['paragraphs', 'headings']):
    """Scrape only specific types of content"""
    all_content = scrape_page_enhanced(url)
    
    if not all_content:
        return None
    
    filtered_content = {}
    for content_type in content_types:
        if content_type in all_content:
            filtered_content[content_type] = all_content[content_type]
    
    return filtered_content

def scrape_with_custom_selectors(url, custom_selectors):
    """
    Scrape using custom CSS selectors
    
    Args:
        url (str): URL to scrape
        custom_selectors (dict): Dictionary of selector names and CSS selectors
    
    Example:
        selectors = {
            'articles': 'article.post',
            'titles': 'h1.title, h2.title',
            'content': '.content p'
        }
    """
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        results = {}
        
        for name, selector in custom_selectors.items():
            elements = soup.select(selector)
            texts = []
            
            for element in elements:
                text = clean_text(element.get_text(separator=' ', strip=True))
                if text:
                    texts.append(text)
            
            results[name] = texts
        
        return results
        
    except Exception as e:
        print(f"Error scraping {url}: {e}")
        return None

# Example usage
if __name__ == "__main__":
    # Test the enhanced scraper
    url = "https://example.com"
    
    # Get all content types
    all_content = scrape_page_enhanced(url)
    if all_content:
        print("Paragraphs found:", len(all_content['paragraphs']))
        print("Headings found:", len(all_content['headings']))
        print("Lists found:", len(all_content['lists']))
    
    # Get only specific content
    specific_content = scrape_specific_content(url, ['paragraphs', 'headings'])
    
    # Use custom selectors
    custom_selectors = {
        'main_content': 'main p, .content p',
        'article_titles': 'h1, h2.title',
        'quotes': 'blockquote'
    }
    custom_content = scrape_with_custom_selectors(url, custom_selectors)
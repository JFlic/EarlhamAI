import psycopg2
import pandas as pd
import os
import re
import json
import glob
from pathlib import Path
from typing import List, Dict, Any, Tuple
from dotenv import load_dotenv
from langchain_docling.loader import ExportType
from langchain_docling import DoclingLoader
from docling.chunking import HybridChunker
from sentence_transformers import SentenceTransformer
import torch
import datetime
import time

# Load environment variables from .env file
load_dotenv()
POSTGRESPASS = os.environ.get("POSTGRESPASS")

process_start = time.time()

# Get the directory where this script is located
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DOC_LOAD_DIR = os.path.join(SCRIPT_DIR, "TempDocumentStore")
CSV_FILE = os.path.join(SCRIPT_DIR, "discovered_files.csv")

# Constants
EMBED_MODEL_ID = "BAAI/bge-m3"
EXPORT_TYPE = ExportType.DOC_CHUNKS

# Create the chunker for document processing
chunker = HybridChunker(
    tokenizer=EMBED_MODEL_ID,
    max_tokens=500,
    overlap_tokens=50,
    split_by_paragraph=True,
    min_tokens=50
)

def find_url(csv_file, document_name):

    df = pd.read_csv(csv_file)
    result = df.loc[df.iloc[:, 2] == document_name, df.columns[0]]
    return result.values[0]

def validate_docx_file(file_path):
    """
    Validate if a DOCX file is properly formatted by checking its ZIP structure.
    
    Parameters:
    file_path (str): Path to the DOCX file to validate.
    
    Returns:
    bool: True if file is valid, False otherwise.
    """
    try:
        import zipfile
        with zipfile.ZipFile(file_path, 'r') as zip_file:
            # Check if it contains the essential DOCX files
            required_files = ['word/document.xml', '[Content_Types].xml']
            file_list = zip_file.namelist()
            
            for required_file in required_files:
                if required_file not in file_list:
                    print(f"Missing required file in DOCX: {required_file}")
                    return False
            
            return True
    except zipfile.BadZipFile:
        print(f"File is not a valid ZIP file (corrupted DOCX): {file_path}")
        return False
    except Exception as e:
        print(f"Error validating DOCX file {file_path}: {str(e)}")
        return False

def process_file_type(files: List[str], file_type: str, category: str) -> List:
    """
    Process a specific file type and return document chunks.
    This eliminates code duplication across different file types.
    """
    all_splits = []
    
    for file in files:
        # Check if file exists and has content
        if not os.path.exists(file):
            print(f"File does not exist: {file}")
            continue
            
        if os.path.getsize(file) == 0:
            print(f"File is empty: {file}")
            continue
            
        # Additional validation for DOCX files
        if file_type == 'DOCX' and not validate_docx_file(file):
            print(f"Skipping corrupted DOCX file: {file}")
            continue
            
        try:
            print(f"Loading {file_type}: {Path(file).name}")
            loader = DoclingLoader(
                file_path=[file],
                export_type=EXPORT_TYPE,
                chunker=chunker,
            )
            docs = loader.load()

            for doc in docs:
                # Extract and clean metadata
                source_file = None
                headings = None
                timestamp = datetime.datetime.now().isoformat()
                
                if hasattr(doc, 'metadata') and doc.metadata:
                    if 'source' in doc.metadata:
                        source_file = doc.metadata['source']
                    
                    if 'dl_meta' in doc.metadata and 'headings' in doc.metadata['dl_meta']:
                        headings = doc.metadata['dl_meta']['headings'][0] if doc.metadata['dl_meta']['headings'] else None
                
                    # Clean up the source file path
                    source_file = source_file.split("\\")[-1]
                    url = find_url(CSV_FILE, source_file)
                    print(f"downloading {source_file}\nAs {url}")

                # Replace the metadata with simplified version
                doc.metadata = {
                    'source': source_file,
                    'heading': headings,
                    'scraped_at': timestamp,
                    "url": url,
                    "type": category
                }

            all_splits.extend(docs)
            print(f"Successfully processed {file_type}: {Path(file).name}")
            
        except Exception as e:
            print(f"Error processing {file_type} file {Path(file).name}: {str(e)}")
            print(f"Skipping corrupted file and continuing with next file...")
            continue
    
    return all_splits

def process_documents(urlpath, category):
    """Process and ingest documents into PGvectorstore"""
    print("Starting document ingestion process...")
    
    # Define file types and their extensions
    file_types = {
        'PDF': glob.glob(os.path.join(urlpath, "*.pdf")),
        'Markdown': glob.glob(os.path.join(urlpath, "*.md")),
        'DOCX': glob.glob(os.path.join(urlpath, "*.docx")),
        'CSV': glob.glob(os.path.join(urlpath, "*.csv")),
        'text': glob.glob(os.path.join(urlpath, "*.txt")),
        'HTML': glob.glob(os.path.join(urlpath, "*.html")),
        'DOC': glob.glob(os.path.join(urlpath, "*.doc"))
    }

    print(f"Processing {len(file_types['PDF'])} PDFs, {len(file_types['Markdown'])} Markdown, "
          f"{len(file_types['DOCX'])} DOCX, {len(file_types['CSV'])} CSV files, "
          f"{len(file_types['text'])} Text, {len(file_types['DOC'])} DOC and {len(file_types['HTML'])} HTML")

    # Process all file types using the unified function
    all_splits = []
    for file_type, files in file_types.items():
        if files:  # Only process if files exist
            splits = process_file_type(files, file_type, category)
            all_splits.extend(splits)
    
    print(f"Total document chunks created: {len(all_splits)}")
    return all_splits

def get_embedding(text: str) -> List[float]:
    "Generate embedding for text using BAAI/bge-m3"
    print("Starting document embedding process...")
    start_time = time.time()
    
    # Initialize the model (only done once and cached)
    if not hasattr(get_embedding, "model"):
        model_init_start = time.time()
        # Specifically use the BAAI/bge-m3 model from HuggingFace
        get_embedding.model = SentenceTransformer(EMBED_MODEL_ID)
        
        # Move model to GPU if available
        if torch.cuda.is_available():
            get_embedding.model = get_embedding.model.to(torch.device('cuda'))
        model_init_end = time.time()
        print(f"TIMING: Embedding model initialization took {model_init_end - model_init_start:.4f} seconds")
    
    # Generate embedding
    # The SentenceTransformer library handles tokenization, encoding, and normalization
    encode_start = time.time()
    embedding = get_embedding.model.encode(
        text,
        normalize_embeddings=True,  # Ensure vectors are normalized (important for BGE models)
        convert_to_numpy=True,      # Convert to numpy array for efficiency
        show_progress_bar=True 
    )
    encode_end = time.time()
    print(f"TIMING: Text encoding took {encode_end - encode_start:.4f} seconds")
    
    # Convert to list and return
    end_time = time.time()
    print(f"TIMING: get_embedding took {end_time - start_time:.4f} seconds")
    return embedding.tolist()

class VectorDB:
    def __init__(self, conn_params: Dict[str, Any]):
        """Initialize the vector database with connection parameters."""
        start_time = time.time()
        self.conn_params = conn_params
        self.conn = psycopg2.connect(**conn_params)
        self.setup_database()
        end_time = time.time()
        print(f"TIMING: VectorDB initialization took {end_time - start_time:.4f} seconds")
    
    def setup_database(self):
        """Set up the necessary database tables and extensions."""
        start_time = time.time()
        with self.conn.cursor() as cursor:
            try:
                # Create pgvector extension if it doesn't exist
                cursor.execute("""
                CREATE EXTENSION IF NOT EXISTS vector;
                """)
                
                # Create documents table if it doesn't exist
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS documents (
                    id SERIAL PRIMARY KEY,
                    content TEXT NOT NULL,
                    metadata JSONB,
                    embedding vector(1024)
                );
                """)
                
                # Try to create an index for faster similarity search
                try:
                    cursor.execute("""
                    CREATE INDEX IF NOT EXISTS embedding_idx ON documents 
                    USING ivfflat (embedding vector_l2_ops)
                    WITH (lists = 100);
                    """)
                except Exception as e:
                    print(f"Warning: Could not create IVFFlat index: {e}")
                    print("Creating simple L2 index instead...")
                    cursor.execute("""
                    CREATE INDEX IF NOT EXISTS embedding_idx ON documents 
                    USING btree (embedding);
                    """)
                
                self.conn.commit()
            except Exception as e:
                print(f"Database setup error: {e}")
                print("If the pgvector extension is not available, please install it first.")
                self.conn.rollback()
        end_time = time.time()
        print(f"TIMING: Database setup took {end_time - start_time:.4f} seconds")
    
    def add_documents(self, documents: List[str], metadatas: List[Dict] = None):
        """Add documents and their embeddings to the database."""
        if metadatas is None:
            metadatas = [{}] * len(documents)
        
        with self.conn.cursor() as cursor:
            for doc, metadata in zip(documents, metadatas):
                embedding = get_embedding(doc)
                # Format the embedding as a PostgreSQL vector using the proper format
                embedding_str = "[" + ",".join(str(x) for x in embedding) + "]"
                
                cursor.execute(
                    """
                    INSERT INTO documents (content, metadata, embedding)
                    VALUES (%s, %s, %s::vector)
                    RETURNING id
                    """,
                    (doc, json.dumps(metadata), embedding_str)
                )
            
            self.conn.commit()
    
    def similarity_search(self, query: str, k: int = 5, hybrid_ratio: float = 0.5) -> List[Dict[str, Any]]:
        """
        Perform hybrid similarity search (vector + BM25-like) to find documents similar to the query.
        Returns the top k most similar documents after re-ranking.
        
        Args:
            query: The query string
            k: The number of results to return
            hybrid_ratio: Balance between vector and keyword search (0.0 = all keyword, 1.0 = all vector)
        """
        start_time = time.time()
        # Get vector embedding
        embed_start = time.time()
        query_embedding = get_embedding(query)
        embed_end = time.time()
        print(f"TIMING: Query embedding generation took {embed_end - embed_start:.4f} seconds")
        
        # Prepare query for keyword search - extract meaningful terms
        keyword_start = time.time()
        keywords = self._extract_keywords(query)
        keyword_end = time.time()
        print(f"TIMING: Keyword extraction took {keyword_end - keyword_start:.4f} seconds")
        
        keyword_clause = ""
        
        if keywords:
            # Create a text search query with weights for keyword matching
            keyword_clause = "ts_rank(to_tsvector('english', content), to_tsquery('english', %s)) * (1 - %s) +"
        
        db_query_start = time.time()
        with self.conn.cursor() as cursor:
            # Format the query embedding as a PostgreSQL vector
            query_embedding_str = "[" + ",".join(str(x) for x in query_embedding) + "]"
            
            sql_query = f"""
            SELECT id, content, metadata, 
                {keyword_clause if keywords else ""} (1 - (embedding <=> %s::vector)) * %s as hybrid_score
            FROM documents
            WHERE 1=1
            """
            
            # Add keyword filter for first-stage retrieval if we have keywords
            # This helps narrow down candidates before vector similarity
            if keywords:
                sql_query += " AND to_tsvector('english', content) @@ to_tsquery('english', %s)"
                
            sql_query += """
            ORDER BY hybrid_score DESC
            LIMIT %s * 5
            """
            
            # Prepare parameters
            params = []
            if keywords:
                params.extend([keywords, hybrid_ratio])
            params.extend([query_embedding_str, hybrid_ratio if keywords else 1.0])
            if keywords:
                params.append(keywords)
            params.append(k)
            
            sql_exec_start = time.time()
            cursor.execute(sql_query, tuple(params))
            sql_exec_end = time.time()
            print(f"TIMING: SQL execution took {sql_exec_end - sql_exec_start:.4f} seconds")
            
            # First-stage retrieval results
            fetch_start = time.time()
            candidates = []
            for doc_id, content, metadata, score in cursor.fetchall():
                candidates.append({
                    "id": doc_id,
                    "content": content,
                    "metadata": metadata,
                    "score": score
                })
            fetch_end = time.time()
            print(f"TIMING: Result fetching took {fetch_end - fetch_start:.4f} seconds")
        db_query_end = time.time()
        print(f"TIMING: Database query total took {db_query_end - db_query_start:.4f} seconds")
        
        # Perform re-ranking using cross-encoder scoring or more detailed similarity
        rerank_start = time.time()
        reranked_results = self._rerank_results(query, candidates)
        rerank_end = time.time()
        print(f"TIMING: Result re-ranking took {rerank_end - rerank_start:.4f} seconds")
        
        end_time = time.time()
        print(f"TIMING: Total similarity_search function took {end_time - start_time:.4f} seconds")
        
        # Return top-k after re-ranking
        return reranked_results[:k]

    def _extract_keywords(self, query: str) -> str:
        """
        Extract meaningful keywords from the query for text search.
        Returns a formatted string for PostgreSQL ts_query.
        """
        start_time = time.time()
        # Remove stop words and special characters
        stop_words = {"a", "an", "the", "and", "or", "but", "is", "are", "in", "on", "at", "to", "for", "with"}
        words = re.findall(r'\b\w+\b', query.lower())
        
        # Filter out stop words and short terms
        keywords = [word for word in words if word not in stop_words and len(word) > 2]
        
        if not keywords:
            end_time = time.time()
            print(f"TIMING: _extract_keywords took {end_time - start_time:.4f} seconds (no keywords found)")
            return ""
        
        # Format for PostgreSQL tsquery (word1 | word2 | word3)
        result = " | ".join(keywords)
        end_time = time.time()
        print(f"TIMING: _extract_keywords took {end_time - start_time:.4f} seconds")
        return result

    def _rerank_results(self, query: str, candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Re-rank the candidate results using a more sophisticated scoring method.
        This could use a cross-encoder or more detailed similarity calculation.
        """
        start_time = time.time()
        # For BAAI/bge-m3, ideally you would use a cross-encoder here
        # But as a simple implementation, we can use a combination of:
        # 1. Exact phrase match bonus
        # 2. Keyword density
        # 3. Original hybrid score
        
        for doc in candidates:
            content = doc["content"].lower()
            query_lower = query.lower()
            
            # Exact phrase match bonus (1.5x boost if exact query appears)
            exact_match_bonus = 1.5 if query_lower in content else 1.0
            
            # Keyword density check
            keywords = self._extract_keywords(query).split(" | ")
            keyword_count = sum(1 for keyword in keywords if keyword in content)
            keyword_density = keyword_count / len(keywords) if keywords else 0
            
            # Compute final score - original score plus bonuses
            final_score = doc["score"] * exact_match_bonus * (1 + keyword_density * 0.5)
            doc["final_score"] = final_score
        
        # Sort by final score
        sorted_results = sorted(candidates, key=lambda x: x.get("final_score", 0), reverse=True)
        end_time = time.time()
        print(f"TIMING: _rerank_results took {end_time - start_time:.4f} seconds")
        return sorted_results

    def get_document_count(self) -> int:
        """Get the total number of documents in the database."""
        with self.conn.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM documents")
            return cursor.fetchone()[0]

    def close(self):
        """Close the database connection."""
        start_time = time.time()
        if self.conn:
            self.conn.close()
        end_time = time.time()
        print(f"TIMING: Database connection close took {end_time - start_time:.4f} seconds")

    def is_connected(self):
        """Check if the database connection is still valid."""
        try:
            with self.conn.cursor() as cursor:
                cursor.execute("SELECT 1")
                return True
        except:
            return False

    def reconnect(self):
        """Reconnect to the database if connection is lost."""
        if not self.is_connected():
            self.conn = psycopg2.connect(**self.conn_params)
import time
import os
import datetime
import re
from dotenv import load_dotenv
from langchain_community.llms import Ollama
from langchain_core.prompts import PromptTemplate
from langchain.chains import create_retrieval_chain
from langchain.chains.combine_documents import create_stuff_documents_chain
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from typing import List, Dict, Any, Tuple
from pydantic import Field
import langdetect
from langdetect.lang_detect_exception import LangDetectException
import asyncio
from concurrent.futures import ThreadPoolExecutor
import threading

from VectorTools import VectorDB

# Load environment variables from .env file
load_dotenv()
POSTGRESPASS = os.environ.get("POSTGRESPASS")

# Connection parameters
CONN_PARAMS = {
    "host": "localhost",
    "port": 5432,
    "database": "Earlham",
    "user": "postgres",
    "password": POSTGRESPASS
}

# Thread-local storage for LLM instances
thread_local = threading.local()

# Global connection pool for database connections
db_connection_pool = []
db_pool_lock = threading.Lock()
MAX_DB_CONNECTIONS = 10

def get_db_connection():
    """Get a database connection from the pool or create a new one."""
    with db_pool_lock:
        if db_connection_pool:
            return db_connection_pool.pop()
        else:
            return VectorDB(CONN_PARAMS)

def return_db_connection(vector_db):
    """Return a database connection to the pool."""
    with db_pool_lock:
        if len(db_connection_pool) < MAX_DB_CONNECTIONS:
            db_connection_pool.append(vector_db)
        else:
            vector_db.close()

def get_llm_instance():
    """Get or create an LLM instance for the current thread."""
    if not hasattr(thread_local, 'llm'):
        thread_local.llm = Ollama(
            model="qwen3:4b",
            base_url="http://localhost:11434",
            temperature=0.2,
            top_p=0.95
        )
    return thread_local.llm

def create_prompt_template(language: str = "English") -> PromptTemplate:
    """
    Create a prompt template for the specified language.
    This eliminates the need for separate PROMPT and SPANISH_PROMPT templates.
    """
    language_instruction = "" if language == "English" else "Respond in Spanish."
    
    return PromptTemplate.from_template(
        f""""role": "You are an AI assistant for the FreedomRacing. Which is a Tool and Auto,
        LLC that offers a huge selection of automotive specialty tools and specialty car parts for mechanics.
        You can provide information, answer questions and perform other tasks as needed.
        Today's date is {{current_date}}. Please be aware of this when discussing events, 
        deadlines, or time-sensitive information.
        Don't repeat queries. {language_instruction}" 
        
        \n---------------------\n{{context}}\n---------------------\n
        
        Given the context information and not prior knowledge, answer the query{"" if language == "English" else " in Spanish"}.
        If the context is empty say that you don't have any information about the question{"" if language == "English" else " in Spanish"}.
        Don't give sources.
        At the end tell the user that if they have anymore questions to let you know.
        Format your response in proper markdown with formatting symbols.
        
        2. Use line breaks between paragraphs (two newlines).
        3. For any lists:
           - Use bullet points with a dash (-) and a space before each item
           - Leave a line break before the first list item
           - Each list item should be on its own line
        4. For numbered lists:
           - Use numbers followed by a period (1. )
           - Leave a line break before the first list item
           - Each numbered item should be on its own line
        5. For section headings, use ## (double hash) with a space after.
        6. Make important terms **bold** using double asterisks.
        7. If you include code blocks, use triple backticks with the language name.
        8. Do not use line breaks within the same paragraph.
        
        \nQuery: {{input}}\nAnswer:\n"""
    )

def detect_language_and_translate(query: str) -> List[str]:
    """
    Detects if the query is in Spanish or English and translates if necessary.
    Returns a list where:
    - First element is "Spanish" or "English"
    - Second element is the English translation if Spanish, or the original query if English
    """
    start_time = time.time()
    llm = get_llm_instance()
    
    # Create translate prompt template
    translate_prompt = PromptTemplate.from_template(
        "Translate the following Spanish text to English, keep the meaning and don't add any extra text, just the translation: {query}"
    )
    
    try:
        lang = langdetect.detect(query)
    except LangDetectException:
        lang = 'en'  # Default to English if detection fails

    if lang == 'es':
        language = "Spanish"
        # Translate from Spanish to English
        translation_prompt = translate_prompt.format(query=query)
        llm_start = time.time()
        translation = llm.predict(translation_prompt).strip()
        llm_end = time.time()
        print(f"TIMING: Spanish translation LLM call took {llm_end - llm_start:.4f} seconds")
    else:
        language = "English"
        translation = query
    
    end_time = time.time()
    print(f"TIMING: detect_language_and_translate took {end_time - start_time:.4f} seconds")
    return [language, translation]

def create_rag_chain(documents: List[Document], language: str, current_date: str):
    """
    Create a RAG chain for the specified language.
    This consolidates the chain creation logic that was duplicated.
    """
    llm = get_llm_instance()
    prompt_template = create_prompt_template(language)
    question_answer_chain = create_stuff_documents_chain(llm, prompt_template.partial(current_date=current_date))
    retriever = SimpleRetriever(documents=documents)

    return create_retrieval_chain(
        retriever=retriever,
        combine_docs_chain=question_answer_chain
    )

def extract_sources(results: List[Dict]) -> List[Dict]:
    """
    Extract source information from search results.
    This consolidates the source extraction logic.
    """
    sources = []
    for result in results:
        if result['metadata'].get('source') == 'Enactus Room Dataset.md':
            source_info = {
                "heading": result['metadata'].get('heading', 'Unknown Title'),
                "source": result['metadata'].get('source', 'None'),
                "url": result['metadata'].get('url', None),
                "page": result['metadata'].get('page', None)
            }
            sources.append(source_info)
            break
        else:
            source_info = {
                "heading": result['metadata'].get('heading', 'Unknown Title'),
                "source": result['metadata'].get('source', 'None'),
                "url": result['metadata'].get('url', None),
                "page": result['metadata'].get('page', None)
            }
            sources.append(source_info)
    return sources

async def process_query(query: str) -> Dict[str, Any]:
    start_time = time.time()
    
    try:
        # Get database connection from pool
        vector_db = get_db_connection()
        
        try:
            # Detect language and translate if necessary
            lang_start = time.time()
            language_info = detect_language_and_translate(query)
            lang_end = time.time()
            print(f"TIMING: Language detection and translation took {lang_end - lang_start:.4f} seconds")
            print(language_info)
            
            # language_info[0] is "Spanish" or "English"
            # language_info[1] is the translated query (or original if English)
            detected_language = language_info[0]
            search_query = language_info[1]  # Use the English query for vector search
            
            # Get current date for including in prompt
            current_date = datetime.datetime.now().strftime("%A, %B %d, %Y")
            
            # Perform similarity search
            vector_start = time.time()
            print(f"DEBUG: About to perform vector search with query: {search_query}")
            results = vector_db.similarity_search(search_query, k=5)
            vector_end = time.time()
            for result in results:
                print(Document(page_content=result['content']))
            print(f"TIMING: Vector similarity search took {vector_end - vector_start:.4f} seconds")
            print(f"DEBUG: Found {len(results)} results from vector search")
            
            # Extract sources from results
            sources = extract_sources(results)

            # Convert results to Document objects
            documents = [Document(page_content=result['content'], metadata=result['metadata']) for result in results]
            print(f"DEBUG: Created {len(documents)} Document objects")


            # Create RAG chain for the detected language
            llm_start = time.time()
            rag_chain = create_rag_chain(documents, detected_language, current_date)
            
            # Get response using the English query
            print(f"DEBUG: About to invoke RAG chain with query: {search_query}")
            response = rag_chain.invoke({"input": search_query})

            # Remove <think>...</think> content
            if response.get("answer"):
                response["answer"] = re.sub(r"<think>.*?</think>", "", response["answer"], flags=re.DOTALL).strip()

            llm_end = time.time()
            print(f"TIMING: LLM response generation took {llm_end - llm_start:.4f} seconds")
            
            end_time = time.time()
            print(f"TIMING: Total process_query function took {end_time - start_time:.4f} seconds")
            
            return {
                "answer": response["answer"],
                "sources": sources,
                "language_info": language_info
            }
                
        finally:
            # Always return the database connection to the pool
            return_db_connection(vector_db)
            
    except Exception as e:
        end_time = time.time()
        print(f"TIMING: process_query function failed after {end_time - start_time:.4f} seconds")
        print(f"ERROR DETAILS: {str(e)}")
        import traceback
        print(f"TRACEBACK: {traceback.format_exc()}")
        return {"error": str(e)}

class SimpleRetriever(BaseRetriever):
    documents: List[Document] = Field(default_factory=list)

    def _get_relevant_documents(self, query: str) -> List[Document]:
        return self.documents

if __name__ == "__main__":
    # Test the query processing
    process_start = time.time()
    
    # Test with an English query
    test_query = "Tell me about City Council"
    print(f"Testing with English query: {test_query}")
    result = process_query(test_query)
    print(f"Language detection: {result.get('language_info', ['Unknown', ''])}")
    
    # Test with a Spanish query
    test_query_spanish = "Háblame del Concejo Municipal"
    print(f"Testing with Spanish query: {test_query_spanish}")
    result_spanish = process_query(test_query_spanish)
    print(f"Language detection: {result_spanish.get('language_info', ['Unknown', ''])}")
    
    # Close connection
   # if vector_db:
    #    vector_db.close()

    # End Time
    process_end = time.time()
    elapsed_time = process_end - process_start

    # Convert to days, hours, minutes, and seconds
    days = int(elapsed_time // (24 * 3600))
    elapsed_time %= (24 * 3600)
    hours = int(elapsed_time // 3600)
    elapsed_time %= 3600
    minutes = int(elapsed_time // 60)
    seconds = elapsed_time % 60

    print(f"\nTotal process execution time: {days} days, {hours} hours, {minutes} minutes, and {seconds:.2f} seconds")
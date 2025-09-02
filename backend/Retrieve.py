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
from deep_translator import GoogleTranslator

from VectorTools import VectorDB

# Create a shared thread pool for blocking work
thread_pool = ThreadPoolExecutor(max_workers=10)

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
            vector_db.close() #Yeah

LLM_INSTANCE = Ollama(
    model="qwen3:8b",  # quantized for speed
    base_url="http://localhost:11434",
    temperature=0.2,
    top_p=0.95
)

def create_prompt_template(language: str = "English") -> PromptTemplate:
    """
    Create a prompt template for the specified language.
    This eliminates the need for separate PROMPT and SPANISH_PROMPT templates.
    """
    
    return PromptTemplate.from_template(
        f""""role": "You are an AI assistant for the Town of Earlham Iowa.
        You can provide information, answer questions and perform other tasks as needed.
        Today's date is {{current_date}}. Please be aware of this when discussing events, 
        deadlines, or time-sensitive information.
        Don't repeat queries."
        
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
    llm = LLM_INSTANCE
    
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
    llm = LLM_INSTANCE
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

        # 1️⃣ Language detection + translation (fast, in main loop)
        lang_start = time.time()
        try:
            lang = langdetect.detect(query)
        except:
            lang = "en"

        if lang == "es":
            detected_language = "Spanish"
            search_query = GoogleTranslator(source='es', target='en').translate(query)
        else:
            detected_language = "English"
            search_query = query
        lang_end = time.time()
        print(f"TIMING: Language detection+translation took {lang_end - lang_start:.4f} seconds")

        # Get current date for prompt
        current_date = datetime.datetime.now().strftime("%A, %B %d, %Y")

        # 2️⃣ Kick off vector search and prompt creation concurrently
        loop = asyncio.get_event_loop()

        vector_task = loop.run_in_executor(
            thread_pool, lambda: vector_db.similarity_search(search_query, k=3)
        )

        # Prepare prompt template while vector search runs
        prompt_template = create_prompt_template(detected_language)

        # Wait for vector search results
        results = await vector_task
        print(f"DEBUG: Vector similarity search returned {len(results)} results")

        # 3️⃣ Process documents
        sources = extract_sources(results)
        documents = [
            Document(page_content=r['content'][:1000], metadata=r['metadata'])
            for r in results
        ]

        # 4️⃣ Create RAG chain
        question_answer_chain = create_stuff_documents_chain(
            LLM_INSTANCE,
            prompt_template.partial(current_date=current_date)
        )
        retriever = SimpleRetriever(documents=documents)
        rag_chain = create_retrieval_chain(retriever, question_answer_chain)

        # 5️⃣ Run LLM in thread pool (doesn’t block other users)
        llm_task = loop.run_in_executor(
            thread_pool, lambda: rag_chain.invoke({"input": search_query})
        )
        response = await llm_task

        # Remove <think>...</think> tags if present
        if response.get("answer"):
            response["answer"] = re.sub(
                r"<think>.*?</think>", "", response["answer"], flags=re.DOTALL
            ).strip()

        total_time = time.time() - start_time
        print(f"TIMING: Total process_query took {total_time:.4f} seconds")

        return {
            "answer": response.get("answer", ""),
            "sources": sources,
            "language_info": [detected_language, search_query]
        }

    except Exception as e:
        print(f"ERROR: process_query failed after {time.time() - start_time:.4f} seconds")
        print(f"DETAILS: {str(e)}")
        import traceback
        print(traceback.format_exc())
        return {"error": str(e)}

    finally:
        return_db_connection(vector_db)

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
#!/usr/bin/env python3
"""
Simple test to see LLM streaming output in terminal in real-time.
This will help you verify that streaming works before implementing it in the web interface.
"""

import asyncio
import time
from langchain_community.llms import Ollama
from langchain_core.prompts import PromptTemplate
from langchain.chains import create_retrieval_chain
from langchain.chains.combine_documents import create_stuff_documents_chain
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from pydantic import Field
from typing import List
import datetime

# Create LLM instance
llm = Ollama(
    model="qwen3:4b",  # Using your current model
    base_url="http://localhost:11434",
    temperature=0.2,
    top_p=0.95
)

class SimpleRetriever(BaseRetriever):
    documents: List[Document] = Field(default_factory=list)

    def _get_relevant_documents(self, query: str) -> List[Document]:
        return self.documents

def create_simple_prompt():
    """Create a simple prompt for testing"""
    return PromptTemplate.from_template(
        """You are an AI assistant for the Town of Earlham Iowa.
        Today's date is {current_date}.
        
        Answer the following question about Earlham:
        Question: {input}
        
        Answer:"""
    )

async def test_simple_streaming():
    """Test simple streaming without RAG - just direct LLM streaming"""
    print("🧪 Testing Simple LLM Streaming")
    print("=" * 50)
    
    query = "Tell me about the City Council in Earlham"
    current_date = datetime.datetime.now().strftime("%A, %B %d, %Y")
    
    print(f"Query: {query}")
    print(f"Date: {current_date}")
    print("\nStreaming response:")
    print("-" * 30)
    
    start_time = time.time()
    
    try:
        # Create a simple prompt
        prompt = create_simple_prompt()
        
        # Create a simple chain
        chain = prompt | llm
        
        # Stream the response
        print("AI: ", end="", flush=True)
        
        full_response = ""
        for chunk in chain.stream({"input": query, "current_date": current_date}):
            if chunk:
                print(chunk, end="", flush=True)
                full_response += chunk
        
        print("\n" + "-" * 30)
        end_time = time.time()
        print(f"✅ Streaming complete in {end_time - start_time:.2f} seconds")
        print(f"📝 Total response length: {len(full_response)} characters")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")

async def test_rag_streaming():
    """Test streaming with RAG (similar to your current setup)"""
    print("\n🧪 Testing RAG Streaming")
    print("=" * 50)
    
    query = "Tell me about City Council meetings"
    current_date = datetime.datetime.now().strftime("%A, %B %d, %Y")
    
    print(f"Query: {query}")
    print(f"Date: {current_date}")
    print("\nStreaming response:")
    print("-" * 30)
    
    start_time = time.time()
    
    try:
        # Create some sample documents (you can replace with real ones)
        sample_docs = [
            Document(
                page_content="The Earlham City Council meets on the first Monday of each month at 7:00 PM in City Hall.",
                metadata={"source": "City Council Info", "heading": "Meeting Schedule"}
            ),
            Document(
                page_content="City Council members are elected officials who serve 4-year terms and make decisions about city policies and budgets.",
                metadata={"source": "City Council Info", "heading": "Council Members"}
            )
        ]
        
        # Create prompt
        prompt = PromptTemplate.from_template(
            """You are an AI assistant for the Town of Earlham Iowa.
            Today's date is {current_date}.
            
            Use the following context to answer the question:
            Context: {context}
            
            Question: {input}
            
            Answer:"""
        )
        
        # Create RAG chain
        retriever = SimpleRetriever(documents=sample_docs)
        question_answer_chain = create_stuff_documents_chain(llm, prompt.partial(current_date=current_date))
        rag_chain = create_retrieval_chain(retriever, question_answer_chain)
        
        # Stream the response
        print("🤖 AI: ", end="", flush=True)
        
        full_response = ""
        for chunk in rag_chain.stream({"input": query}):
            if "answer" in chunk:
                answer = chunk["answer"]
                if answer and answer != full_response:
                    # Get only the new part
                    if answer.startswith(full_response):
                        new_part = answer[len(full_response):]
                        if new_part:
                            print(new_part, end="", flush=True)
                            full_response = answer
        
        print("\n" + "-" * 30)
        end_time = time.time()
        print(f"✅ RAG Streaming complete in {end_time - start_time:.2f} seconds")
        print(f"📝 Total response length: {len(full_response)} characters")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")

async def main():
    """Run both tests"""
    print("🚀 Earlham AI Streaming Test")
    print("=" * 60)
    print("This will test LLM streaming output in your terminal")
    print("=" * 60)
    
    # Test 1: Simple streaming
    await test_simple_streaming()
    
    # Wait a moment
    await asyncio.sleep(2)
    
    # Test 2: RAG streaming
    await test_rag_streaming()
    
    print("\n🎉 All tests completed!")
    print("\nIf you see text appearing character by character above, streaming is working!")

if __name__ == "__main__":
    asyncio.run(main())
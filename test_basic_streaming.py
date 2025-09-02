#!/usr/bin/env python3
"""
Ultra-simple test to see if LLM streaming works at all.
This just tests the basic Ollama streaming functionality.
"""

import asyncio
from langchain_community.llms import Ollama

def test_basic_streaming():
    """Test the most basic streaming possible"""
    print("🧪 Testing Basic LLM Streaming")
    print("=" * 40)
    
    # Create LLM instance
    llm = Ollama(
        model="qwen3:4b",
        base_url="http://localhost:11434",
        temperature=0.2,
        top_p=0.95
    )
    
    query = "Tell me about Earlham Iowa in 3 sentences."
    
    print(f"Query: {query}")
    print("\nStreaming response:")
    print("-" * 20)
    print("🤖 AI: ", end="", flush=True)
    
    try:
        # This is the simplest possible streaming test
        for chunk in llm.stream(query):
            if chunk:
                print(chunk, end="", flush=True)
        
        print("\n" + "-" * 20)
        print("✅ Basic streaming test complete!")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        print("Make sure Ollama is running on localhost:11434")

if __name__ == "__main__":
    test_basic_streaming()
#!/usr/bin/env python3
"""
Test script to verify the streaming API endpoint works.
This will test the /query/stream endpoint directly.
"""

import asyncio
import aiohttp
import json
import time

async def test_streaming_api():
    """Test the streaming API endpoint"""
    url = "http://127.0.0.1:8001/query/stream"
    test_query = "Tell me about City Council"
    
    print(f"🧪 Testing Streaming API Endpoint")
    print("=" * 50)
    print(f"Query: {test_query}")
    print("\nStreaming response:")
    print("-" * 30)
    
    start_time = time.time()
    
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(
                url,
                json={"query": test_query},
                headers={"Content-Type": "application/json"}
            ) as response:
                
                if response.status != 200:
                    print(f"❌ Error: HTTP {response.status}")
                    return
                
                print("🤖 AI: ", end="", flush=True)
                
                async for line in response.content:
                    line_str = line.decode('utf-8').strip()
                    if line_str.startswith('data: '):
                        try:
                            data = json.loads(line_str[6:])
                            if data['type'] == 'start':
                                print(f"🚀 Started processing (User ID: {data['user_id']})")
                            elif data['type'] == 'sources':
                                print(f"\n📚 Sources found: {len(data['sources'])}")
                                for source in data['sources']:
                                    print(f"   - {source.get('source', 'Unknown')}")
                                print("\n🤖 AI: ", end="", flush=True)
                            elif data['type'] == 'content':
                                print(data['content'], end="", flush=True)
                            elif data['type'] == 'metadata':
                                print(f"\n📊 Processing time: {data['metadata'].get('processing_time', 'Unknown')}")
                            elif data['type'] == 'done':
                                print("\n✅ Streaming complete!")
                            elif data['type'] == 'error':
                                print(f"\n❌ Error: {data['error']}")
                        except json.JSONDecodeError:
                            print(f"⚠️  Could not parse: {line_str}")
                
                end_time = time.time()
                print("-" * 30)
                print(f"Total time: {end_time - start_time:.2f} seconds")
                
        except Exception as e:
            print(f"❌ Test failed: {e}")
            print("Make sure your API server is running on http://127.0.0.1:8001")

async def main():
    """Run the test"""
    print("🚀 Earlham AI Streaming API Test")
    print("=" * 60)
    print("This will test the streaming endpoint directly")
    print("=" * 60)
    
    await test_streaming_api()
    
    print("\n🎉 Test completed!")
    print("\nIf you see text appearing character by character above, streaming is working!")

if __name__ == "__main__":
    asyncio.run(main())
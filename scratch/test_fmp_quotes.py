import asyncio
import aiohttp

async def test_endpoint(session, url):
    async with session.get(url) as response:
        print(f"URL: {url}")
        print(f"Status: {response.status}")
        text = await response.text()
        print(f"Response: {text[:300]}")
        print("-" * 50)

async def main():
    api_key = "J1oSzMPQ3idxfdYRt4lz2e11AFeTwgdj"
    async with aiohttp.ClientSession() as session:
        # Test v3 quote
        await test_endpoint(session, f"https://financialmodelingprep.com/api/v3/quote/AAPL?apikey={api_key}")
        
        # Test stable quote
        await test_endpoint(session, f"https://financialmodelingprep.com/stable/quote/AAPL?apikey={api_key}")
        
        # Test stable quote batch
        await test_endpoint(session, f"https://financialmodelingprep.com/stable/quote?symbol=AAPL,MSFT,GOOG&apikey={api_key}")
        
        # Test stable quote-short
        await test_endpoint(session, f"https://financialmodelingprep.com/stable/quote-short/AAPL?apikey={api_key}")

        # Test v4 quote
        await test_endpoint(session, f"https://financialmodelingprep.com/api/v4/quote?symbol=AAPL&apikey={api_key}")

if __name__ == "__main__":
    asyncio.run(main())

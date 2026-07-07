import asyncio
import aiohttp

async def test_endpoint(session, name, url):
    async with session.get(url) as response:
        print(f"--- {name} ---")
        print("URL:", url)
        print("Status:", response.status)
        text = await response.text()
        print("Response:", text[:200])
        print("-" * 50)

async def main():
    api_key = "J1oSzMPQ3idxfdYRt4lz2e11AFeTwgdj"
    async with aiohttp.ClientSession() as session:
        # 1. Historical bars
        await test_endpoint(session, "v3 Historical", f"https://financialmodelingprep.com/api/v3/historical-price-full/AAPL?apikey={api_key}")
        await test_endpoint(session, "Stable Historical", f"https://financialmodelingprep.com/stable/historical-price-full/AAPL?apikey={api_key}")
        
        # 2. Key metrics
        await test_endpoint(session, "v3 Key Metrics", f"https://financialmodelingprep.com/api/v3/key-metrics-ttm/AAPL?apikey={api_key}")
        await test_endpoint(session, "Stable Key Metrics", f"https://financialmodelingprep.com/stable/key-metrics-ttm/AAPL?apikey={api_key}")
        
        # 3. Stock news
        await test_endpoint(session, "v3 Stock News", f"https://financialmodelingprep.com/api/v3/stock_news?tickers=AAPL&limit=1&apikey={api_key}")
        await test_endpoint(session, "Stable Stock News", f"https://financialmodelingprep.com/stable/stock_news?tickers=AAPL&limit=1&apikey={api_key}")

if __name__ == "__main__":
    asyncio.run(main())

import asyncio
import aiohttp

async def test_endpoint(session, name, url):
    async with session.get(url) as response:
        print(f"--- {name} ---")
        print("URL:", url)
        print("Status:", response.status)
        text = await response.text()
        print("Response:", text[:300])
        print("-" * 50)

async def main():
    api_key = "J1oSzMPQ3idxfdYRt4lz2e11AFeTwgdj"
    async with aiohttp.ClientSession() as session:
        # 1. Test Stable Historical permutations
        await test_endpoint(session, "Stable Historical Query Param", f"https://financialmodelingprep.com/stable/historical-price-full?symbol=AAPL&apikey={api_key}")
        await test_endpoint(session, "Stable Historical Path Param", f"https://financialmodelingprep.com/stable/historical-price-full/AAPL?apikey={api_key}")
        
        # 2. Test Stable Key Metrics permutations
        await test_endpoint(session, "Stable Key Metrics Query Param", f"https://financialmodelingprep.com/stable/key-metrics-ttm?symbol=AAPL&apikey={api_key}")
        await test_endpoint(session, "Stable Key Metrics Path Param", f"https://financialmodelingprep.com/stable/key-metrics-ttm/AAPL?apikey={api_key}")
        
        # 3. Test Stable Stock News permutations
        await test_endpoint(session, "Stable Stock News Query Param Tickers", f"https://financialmodelingprep.com/stable/stock_news?tickers=AAPL&limit=1&apikey={api_key}")
        await test_endpoint(session, "Stable Stock News Query Param Symbol", f"https://financialmodelingprep.com/stable/stock_news?symbol=AAPL&limit=1&apikey={api_key}")

if __name__ == "__main__":
    asyncio.run(main())

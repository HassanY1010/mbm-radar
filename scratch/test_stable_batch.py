import asyncio
import aiohttp

async def main():
    api_key = "J1oSzMPQ3idxfdYRt4lz2e11AFeTwgdj"
    async with aiohttp.ClientSession() as session:
        # Test 1: stable batch-quote
        url1 = f"https://financialmodelingprep.com/stable/batch-quote?symbols=AAPL,MSFT,GOOG&apikey={api_key}"
        async with session.get(url1) as r:
            print("batch-quote status:", r.status)
            if r.status == 200:
                data = await r.json()
                print("batch-quote results count:", len(data))
                print("batch-quote sample:", data[:1])
            else:
                print("batch-quote response:", await r.text())
        
        # Test 2: stable batch-quote-short
        url2 = f"https://financialmodelingprep.com/stable/batch-quote-short?symbols=AAPL,MSFT,GOOG&apikey={api_key}"
        async with session.get(url2) as r:
            print("batch-quote-short status:", r.status)
            if r.status == 200:
                data = await r.json()
                print("batch-quote-short results count:", len(data))
                print("batch-quote-short sample:", data[:1])
            else:
                print("batch-quote-short response:", await r.text())

        # Test 3: legacy /api/v3/quote/AAPL,MSFT
        url3 = f"https://financialmodelingprep.com/api/v3/quote/AAPL,MSFT?apikey={api_key}"
        async with session.get(url3) as r:
            print("v3/quote batch status:", r.status)
            if r.status == 200:
                data = await r.json()
                print("v3/quote batch results count:", len(data))
            else:
                print("v3/quote response:", await r.text())

if __name__ == "__main__":
    asyncio.run(main())

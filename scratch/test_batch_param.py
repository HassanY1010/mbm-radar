import asyncio
import aiohttp

async def main():
    api_key = "J1oSzMPQ3idxfdYRt4lz2e11AFeTwgdj"
    async with aiohttp.ClientSession() as session:
        # Test 1: symbol=AAPL,MSFT
        async with session.get(f"https://financialmodelingprep.com/stable/quote?symbol=AAPL,MSFT&apikey={api_key}") as r:
            print("symbol=AAPL,MSFT:", r.status, await r.text())
            
        # Test 2: symbols=AAPL,MSFT
        async with session.get(f"https://financialmodelingprep.com/stable/quote?symbols=AAPL,MSFT&apikey={api_key}") as r:
            print("symbols=AAPL,MSFT:", r.status, await r.text())
            
        # Test 3: symbols[]=AAPL&symbols[]=MSFT
        async with session.get(f"https://financialmodelingprep.com/stable/quote?symbols[]=AAPL&symbols[]=MSFT&apikey={api_key}") as r:
            print("symbols[]=AAPL&symbols[]=MSFT:", r.status, await r.text())
            
        # Test 4: Path parameter style /stable/quote/AAPL,MSFT
        async with session.get(f"https://financialmodelingprep.com/stable/quote/AAPL,MSFT?apikey={api_key}") as r:
            print("Path style AAPL,MSFT:", r.status, await r.text())

if __name__ == "__main__":
    asyncio.run(main())

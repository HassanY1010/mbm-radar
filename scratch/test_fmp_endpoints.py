import asyncio
import aiohttp

async def test_endpoint(session, name, url):
    async with session.get(url) as response:
        print(f"--- {name} ---")
        print("Status:", response.status)
        if response.status == 200:
            data = await response.json()
            print("Length:", len(data) if isinstance(data, list) else "Not list")
            print("First item:", data[0] if isinstance(data, list) and data else "Empty")
        else:
            print("Error:", await response.text())

async def main():
    api_key = "J1oSzMPQ3idxfdYRt4lz2e11AFeTwgdj"
    async with aiohttp.ClientSession() as session:
        # Test available traded list
        await test_endpoint(
            session, 
            "Available Traded List", 
            f"https://financialmodelingprep.com/api/v3/available-traded/list?apikey={api_key}"
        )
        
        # Test stock list
        await test_endpoint(
            session, 
            "Stock List (v3)", 
            f"https://financialmodelingprep.com/api/v3/stock/list?apikey={api_key}"
        )
        
        # Test exchange-traded symbols
        await test_endpoint(
            session, 
            "Exchange NASDAQ Symbol List", 
            f"https://financialmodelingprep.com/api/v3/symbol/NASDAQ?apikey={api_key}"
        )

if __name__ == "__main__":
    asyncio.run(main())

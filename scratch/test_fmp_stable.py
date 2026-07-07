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
        # Test stable stock-list
        await test_endpoint(
            session, 
            "Stable Stock List", 
            f"https://financialmodelingprep.com/api/v3/stock-list?apikey={api_key}" # Wait, is it /api/v3/stock-list or /stable/stock-list?
        )
        
        # Test /stable/stock-list
        await test_endpoint(
            session, 
            "Stable Stock List (no api)", 
            f"https://financialmodelingprep.com/stable/stock-list?apikey={api_key}"
        )
        
        # Test /v3/quote
        await test_endpoint(
            session, 
            "Quote (v3)", 
            f"https://financialmodelingprep.com/api/v3/quote/AAPL?apikey={api_key}"
        )
        
        # Test /stable/quote
        await test_endpoint(
            session, 
            "Quote (stable)", 
            f"https://financialmodelingprep.com/stable/quote/AAPL?apikey={api_key}"
        )

if __name__ == "__main__":
    asyncio.run(main())

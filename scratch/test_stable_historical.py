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
        # Test stable historical light
        await test_endpoint(session, "Stable Historical Light", f"https://financialmodelingprep.com/stable/historical-price-eod/light?symbol=AAPL&apikey={api_key}")
        
        # Test stable historical full
        await test_endpoint(session, "Stable Historical Full", f"https://financialmodelingprep.com/stable/historical-price-eod/full?symbol=AAPL&apikey={api_key}")

if __name__ == "__main__":
    asyncio.run(main())

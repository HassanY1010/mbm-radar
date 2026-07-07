import asyncio
import aiohttp

async def main():
    api_key = "J1oSzMPQ3idxfdYRt4lz2e11AFeTwgdj"
    # FMP Endpoint to search/filter stocks
    url = f"https://financialmodelingprep.com/api/v3/stock-screener?marketCapMoreThan=1000000000&betaMoreThan=1&volumeMoreThan=100&apikey={api_key}"
    print("Testing FMP API connection...")
    
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            print("Status Code:", response.status)
            if response.status == 200:
                data = await response.json()
                print("Successfully fetched FMP data!")
                print("First 2 results:", data[:2] if isinstance(data, list) else data)
            else:
                text = await response.text()
                print("Error Details:", text)

if __name__ == "__main__":
    asyncio.run(main())

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
        # 1. Historical EOD
        await test_endpoint(session, "Stable Historical EOD", f"https://financialmodelingprep.com/stable/historical-price-eod/AAPL?apikey={api_key}")
        await test_endpoint(session, "Stable Historical EOD Query", f"https://financialmodelingprep.com/stable/historical-price-eod?symbol=AAPL&apikey={api_key}")
        
        # 2. Stable Company Screener by exchange
        await test_endpoint(session, "Stable Screener NASDAQ", f"https://financialmodelingprep.com/stable/company-screener?exchange=NASDAQ&limit=20&apikey={api_key}")
        await test_endpoint(session, "Stable Screener NYSE", f"https://financialmodelingprep.com/stable/company-screener?exchange=NYSE&limit=2&apikey={api_key}")
        await test_endpoint(session, "Stable News raw list", f"https://financialmodelingprep.com/stable/news/stock-latest?limit=2&apikey={api_key}")

if __name__ == "__main__":
    asyncio.run(main())

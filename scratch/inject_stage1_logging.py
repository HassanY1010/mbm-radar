import os

file_path = "app/scanner/scanner_manager.py"
print(f"Reading {file_path}...")
with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

target_loop_start = """                # 2. Stage 1: Fast Screening & Pre-Scoring
                candidate_quotes = []
                for quote in all_quotes:"""

replacement_loop_start = """                # 2. Stage 1: Fast Screening & Pre-Scoring
                candidate_quotes = []
                price_failed = 0
                volume_failed = 0
                market_cap_failed = 0
                float_failed = 0
                change_failed = 0
                gap_failed = 0
                dollar_volume_failed = 0
                excluded_type_failed = 0

                for quote in all_quotes:"""

target_exclusions = """                    # Exclude Chinese, SPAC, ETF, ADR in Stage 1
                    is_excluded = False
                    for ind in ["CHINA", "CHINESE", "SINA", "ALIBABA", "TENCENT", "BAIDU", "JD.COM", "PINDUODUO"]:
                        if ind in company_name or ticker.endswith(".CN"):
                            is_excluded = True
                            break
                    if is_excluded:
                        continue
                        
                    for ind in ["SPAC", "ACQUISITION", "BLANK CHECK", "UNIT", "WARRANT"]:
                        if ind in company_name:
                            is_excluded = True
                            break
                    if is_excluded:
                        continue
                        
                    if "ETF" in company_name or quote.get("isETF") or quote.get("isEtf"):
                        continue
                        
                    if "ADR" in company_name or (len(ticker) == 5 and ticker.endswith("Y")):
                        continue"""

replacement_exclusions = """                    # Exclude Chinese, SPAC, ETF, ADR in Stage 1
                    is_excluded = False
                    for ind in ["CHINA", "CHINESE", "SINA", "ALIBABA", "TENCENT", "BAIDU", "JD.COM", "PINDUODUO"]:
                        if ind in company_name or ticker.endswith(".CN"):
                            is_excluded = True
                            break
                    if is_excluded:
                        excluded_type_failed += 1
                        continue
                        
                    for ind in ["SPAC", "ACQUISITION", "BLANK CHECK", "UNIT", "WARRANT"]:
                        if ind in company_name:
                            is_excluded = True
                            break
                    if is_excluded:
                        excluded_type_failed += 1
                        continue
                        
                    if "ETF" in company_name or quote.get("isETF") or quote.get("isEtf"):
                        excluded_type_failed += 1
                        continue
                        
                    if "ADR" in company_name or (len(ticker) == 5 and ticker.endswith("Y")):
                        excluded_type_failed += 1
                        continue"""

target_criteria = """                    # Basic criteria limits — strict enough to only pass high-momentum candidates
                    if price < 0.10 or price > settings.SCANNER_MAX_PRICE:
                        continue
                    if volume < settings.SCANNER_MIN_VOLUME:
                        continue
                    if market_cap > settings.SCANNER_MAX_MARKET_CAP:
                        continue
                    if float_size > settings.SCANNER_MAX_FLOAT:
                        continue
                    # Require at least 3% change AND 3% gap for a real momentum move
                    if abs(change_pct) < max(3.0, settings.SCANNER_MIN_CHANGE_PCT):
                        continue
                    if abs(gap_pct) < max(3.0, settings.SCANNER_MIN_GAP_PCT):
                        continue"""

replacement_criteria = """                    # Basic criteria limits — strict enough to only pass high-momentum candidates
                    if price < 0.10 or price > settings.SCANNER_MAX_PRICE:
                        price_failed += 1
                        continue
                    if volume < settings.SCANNER_MIN_VOLUME:
                        volume_failed += 1
                        continue
                    if market_cap > settings.SCANNER_MAX_MARKET_CAP:
                        market_cap_failed += 1
                        continue
                    if float_size > settings.SCANNER_MAX_FLOAT:
                        float_failed += 1
                        continue
                    # Require at least 3% change AND 3% gap for a real momentum move
                    if abs(change_pct) < max(3.0, settings.SCANNER_MIN_CHANGE_PCT):
                        change_failed += 1
                        continue
                    if abs(gap_pct) < max(3.0, settings.SCANNER_MIN_GAP_PCT):
                        gap_failed += 1
                        continue"""

target_dollar_vol = """                    dollar_volume = price * volume
                    # Minimum 500k dollar volume to ensure real institutional interest
                    if dollar_volume < 500_000:
                        continue"""

replacement_dollar_vol = """                    dollar_volume = price * volume
                    # Minimum 500k dollar volume to ensure real institutional interest
                    if dollar_volume < 500_000:
                        dollar_volume_failed += 1
                        continue"""

target_log = """                scanner_logger.info(f"Stage 1 screening done. Total active tickers: {len(all_quotes)}. Filtered candidates: {len(candidate_quotes)}. Dynamic Top-K selected: {len(top_k_quotes)}")"""

replacement_log = """                scanner_logger.info(
                    f"Stage 1 screening done. Total active tickers: {len(all_quotes)}. Filtered candidates: {len(candidate_quotes)}. Dynamic Top-K selected: {len(top_k_quotes)} | "
                    f"Exclusions: price={price_failed}, volume={volume_failed}, mcap={market_cap_failed}, float={float_failed}, "
                    f"change={change_failed}, gap={gap_failed}, dollar_vol={dollar_volume_failed}, type_exclusions={excluded_type_failed}"
                )"""

assert target_loop_start in content, "target_loop_start not found"
assert target_exclusions in content, "target_exclusions not found"
assert target_criteria in content, "target_criteria not found"
assert target_dollar_vol in content, "target_dollar_vol not found"
assert target_log in content, "target_log not found"

content = content.replace(target_loop_start, replacement_loop_start)
content = content.replace(target_exclusions, replacement_exclusions)
content = content.replace(target_criteria, replacement_criteria)
content = content.replace(target_dollar_vol, replacement_dollar_vol)
content = content.replace(target_log, replacement_log)

with open(file_path, "w", encoding="utf-8") as f:
    f.write(content)

print("Programmatic injection completed successfully!")

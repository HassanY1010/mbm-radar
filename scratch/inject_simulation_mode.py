"""
Injects simulation-mode changes into scanner_manager.py:
1. is_simulated flag in Signal creation
2. [SIMULATION] log tag in Stage 1 audit
3. Poll interval override in simulation mode
"""

file_path = "app/scanner/scanner_manager.py"
with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

# -------------------------------------------------------------------
# Change 1: Tag Signal with is_simulated=settings.SIMULATION_MODE
# -------------------------------------------------------------------
target_signal_timestamp = "                timestamp=datetime.datetime.utcnow()\n            )"
replacement_signal_timestamp = (
    "                timestamp=datetime.datetime.utcnow(),\n"
    "                is_simulated=settings.SIMULATION_MODE\n"
    "            )"
)
assert target_signal_timestamp in content, "FAILED: Signal timestamp target not found"
content = content.replace(target_signal_timestamp, replacement_signal_timestamp, 1)

# -------------------------------------------------------------------
# Change 2: Add [SIMULATION] prefix to Stage 1 audit log
# -------------------------------------------------------------------
target_stage1_log = (
    '                scanner_logger.info(\n'
    '                    f"Stage 1 screening done. Total active tickers: {len(all_quotes)}. Filtered candidates: {len(candidate_quotes)}. Dynamic Top-K selected: {len(top_k_quotes)} | "\n'
    '                    f"Exclusions: price={price_failed}, volume={volume_failed}, mcap={market_cap_failed}, float={float_failed}, "\n'
    '                    f"change={change_failed}, gap={gap_failed}, dollar_vol={dollar_volume_failed}, type_exclusions={excluded_type_failed}"\n'
    '                )'
)
replacement_stage1_log = (
    '                sim_prefix = "[SIMULATION] " if settings.SIMULATION_MODE else ""\n'
    '                scanner_logger.info(\n'
    '                    f"{sim_prefix}Stage 1 screening done. Total active tickers: {len(all_quotes)}. Filtered candidates: {len(candidate_quotes)}. Dynamic Top-K selected: {len(top_k_quotes)} | "\n'
    '                    f"Exclusions: price={price_failed}, volume={volume_failed}, mcap={market_cap_failed}, float={float_failed}, "\n'
    '                    f"change={change_failed}, gap={gap_failed}, dollar_vol={dollar_volume_failed}, type_exclusions={excluded_type_failed}"\n'
    '                )'
)
assert target_stage1_log in content, "FAILED: Stage 1 audit log target not found"
content = content.replace(target_stage1_log, replacement_stage1_log, 1)

# -------------------------------------------------------------------
# Change 3: Override poll interval in simulation mode
# -------------------------------------------------------------------
target_poll_sleep = "            # Wait before scanning the market again\n            await asyncio.sleep(settings.SCANNER_POLL_INTERVAL_SECONDS)"
replacement_poll_sleep = (
    "            # Wait before scanning the market again\n"
    "            # In simulation mode, use a shorter interval for rapid signal generation\n"
    "            poll_interval = settings.SIMULATION_INTERVAL_SECONDS if settings.SIMULATION_MODE else settings.SCANNER_POLL_INTERVAL_SECONDS\n"
    "            await asyncio.sleep(poll_interval)"
)
assert target_poll_sleep in content, "FAILED: Poll sleep target not found"
content = content.replace(target_poll_sleep, replacement_poll_sleep, 1)

# -------------------------------------------------------------------
# Change 4: Log simulation mode at startup of polling loop
# -------------------------------------------------------------------
target_polling_start = '        scanner_logger.info("Starting stock scanner REST polling loop...")'
replacement_polling_start = (
    '        if settings.SIMULATION_MODE:\n'
    '            scanner_logger.info("[SIMULATION] Stock scanner starting in SIMULATION MODE \u2014 synthetic signals will be generated every "\n'
    '                                f"{settings.SIMULATION_INTERVAL_SECONDS}s through the real pipeline. No real market data will be fetched.")\n'
    '        scanner_logger.info("Starting stock scanner REST polling loop...")'
)
assert target_polling_start in content, "FAILED: Polling start log target not found"
content = content.replace(target_polling_start, replacement_polling_start, 1)

# -------------------------------------------------------------------
# Write back
# -------------------------------------------------------------------
with open(file_path, "w", encoding="utf-8") as f:
    f.write(content)

print("All 4 injections completed successfully in scanner_manager.py!")

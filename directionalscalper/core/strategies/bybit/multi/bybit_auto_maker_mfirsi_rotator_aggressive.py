import time
import math
import logging
import os
import json
import copy
from threading import Thread, Lock
from ...strategy import Strategy
from datetime import datetime, timedelta
from typing import Tuple
import pandas as pd
from ...logger import Logger
### ILAY ###
from live_table_manager import shared_symbols_data
####

logging = Logger(logger_name="BybitRotatorAggressive", filename="BybitRotatorAggressive.log", stream=True)

class BybitRotatorAggressive(Strategy):
    def __init__(self, exchange, manager, config, symbols_allowed=None):
        super().__init__(exchange, config, manager, symbols_allowed)
        self.symbols_allowed = symbols_allowed
        self.manager = manager
        self.all_symbol_data = {}
        # Initialize the last health check time to zero or to the current time
        self.last_health_check_time = 0 #time.time()  # Initialize to the current time
        self.health_check_interval = 600  # 10 minutes
        self.last_long_tp_update = datetime.now()
        self.last_short_tp_update = datetime.now()
        self.next_long_tp_update = self.calculate_next_update_time()
        self.next_short_tp_update = self.calculate_next_update_time()
        self.last_cancel_time = 0
        self.current_wallet_exposure = 1.0
        self.short_tp_distance_percent = 0.0
        self.short_expected_profit_usdt = 0.0
        self.long_tp_distance_percent = 0.0
        self.long_expected_profit_usdt = 0.0
        self.printed_trade_quantities = False
        self.checked_amount_validity = False
        self.long_pos_leverage = 1.0
        self.short_pos_leverage = 1.0
        self.max_long_trade_qty = None
        self.max_short_trade_qty = None
        self.initial_max_long_trade_qty = None
        self.initial_max_short_trade_qty = None
        self.long_leverage_increased = False
        self.short_leverage_increased = False
        self.rows = {} 

    def run(self, symbol):
        threads = [
            Thread(target=self.run_single_symbol, args=(symbol,))
        ]

        for thread in threads:
            thread.start()

        for thread in threads:
            thread.join()

    def run_single_symbol(self, symbol):
        print(f"Running for symbol (inside run_single_symbol method): {symbol}")

        quote_currency = "USDT"
        max_retries = 5
        retry_delay = 5

        # Initialize exchange-related variables outside the live context
        wallet_exposure = self.config.wallet_exposure
        min_dist = self.config.min_distance
        min_vol = self.config.min_volume
        current_leverage = self.exchange.get_current_leverage_bybit(symbol)
        max_leverage = self.exchange.get_max_leverage_bybit(symbol)

        if self.config.dashboard_enabled:
            dashboard_path = os.path.join(self.config.shared_data_path, "shared_data.json")

        logging.info("Setting up exchange")
        self.exchange.setup_exchange_bybit(symbol)

        logging.info("Setting leverage")
        if current_leverage != max_leverage:
            logging.info(f"Current leverage is not at maximum. Setting leverage to maximum. Maximum is {max_leverage}")
            self.exchange.set_leverage_bybit(max_leverage, symbol)

        previous_five_minute_distance = None
        previous_thirty_minute_distance = None
        previous_one_hour_distance = None
        previous_four_hour_distance = None

        while True:  # Outer loop
            rotator_symbols = self.manager.get_auto_rotate_symbols()
            if symbol not in rotator_symbols:
                logging.info(f"Symbol {symbol} not in rotator symbols. Waiting for it to reappear.")
                time.sleep(60)
                continue

            while True:  # Inner loop
                # current_time = time.time()
                # if current_time - self.last_health_check_time > self.health_check_interval:
                #     self.exchange.health_check(interval_seconds=self.health_check_interval)
                #     self.last_health_check_time = current_time

                should_exit = False
                rotator_symbols = self.manager.get_auto_rotate_symbols()
                if symbol not in rotator_symbols:
                    logging.info(f"Symbol {symbol} no longer in rotator symbols. Stopping operations for this symbol.")
                    should_exit = True

                whitelist = self.config.whitelist
                blacklist = self.config.blacklist
                if symbol not in whitelist or symbol in blacklist:
                    logging.info(f"Symbol {symbol} is no longer allowed based on whitelist/blacklist. Stopping operations for this symbol.")
                    should_exit = True

                if should_exit:
                    break

                # Get API data
                api_data = self.manager.get_api_data(symbol)
                one_minute_volume = api_data['1mVol']
                five_minute_distance = api_data['5mSpread']
                trend = api_data['Trend']
                mfirsi_signal = api_data['MFI']
                eri_trend = api_data['ERI Trend']

                quote_currency = "USDT"

                for i in range(max_retries):
                    try:
                        total_equity = self.exchange.get_balance_bybit(quote_currency)
                        break
                    except Exception as e:
                        if i < max_retries - 1:
                            logging.info(f"Error occurred while fetching balance: {e}. Retrying in {retry_delay} seconds...")
                            time.sleep(retry_delay)
                        else:
                            raise e
                        
                #logging.info(f"Total equity: {total_equity}")

                for i in range(max_retries):
                    try:
                        available_equity = self.exchange.get_available_balance_bybit(quote_currency)
                        break
                    except Exception as e:
                        if i < max_retries - 1:
                            logging.info(f"Error occurred while fetching available balance: {e}. Retrying in {retry_delay} seconds...")
                            time.sleep(retry_delay)
                        else:
                            raise e

                #logging.info(f"Available equity: {available_equity}")

                current_price = self.exchange.get_current_price(symbol)
                market_data = self.get_market_data_with_retry(symbol, max_retries = 5, retry_delay = 5)
                #contract_size = self.exchange.get_contract_size_bybit(symbol)
                best_ask_price = self.exchange.get_orderbook(symbol)['asks'][0][0]
                best_bid_price = self.exchange.get_orderbook(symbol)['bids'][0][0]

                # Calculate dynamic amounts and min_qty for each symbol
                long_dynamic_amount, short_dynamic_amount, min_qty = self.calculate_dynamic_amount(
                    symbol, market_data, total_equity, best_ask_price, max_leverage
                )

                self.print_trade_quantities_once_bybit(self.max_long_trade_qty)
                self.print_trade_quantities_once_bybit(self.max_short_trade_qty)

                # Get the 1-minute moving averages
                logging.info(f"Fetching MA data")
                moving_averages = self.get_all_moving_averages(symbol)

                ma_6_high = moving_averages["ma_6_high"]
                ma_6_low = moving_averages["ma_6_low"]
                ma_3_low = moving_averages["ma_3_low"]
                ma_3_high = moving_averages["ma_3_high"]
                ma_1m_3_high = moving_averages["ma_1m_3_high"]
                ma_5m_3_high = moving_averages["ma_5m_3_high"]

                position_data = self.exchange.get_positions_bybit(symbol)

                open_position_data = self.exchange.get_all_open_positions_bybit()

                open_symbols = self.extract_symbols_from_positions_bybit(open_position_data)
                open_symbols = [symbol.replace("/", "") for symbol in open_symbols]

                rotator_symbols = self.manager.get_auto_rotate_symbols()

                # Find symbols that are open but not in rotator
                symbols_to_manage = [s for s in open_symbols if s not in rotator_symbols]

                # Manage these symbols
                for s in symbols_to_manage:
                    print(f"Managing symbol: {s}")  # Debugging line
                    self.manage_open_positions_aggressive([s], total_equity)  # Notice the square brackets around 's'

                can_open_new_position = self.can_trade_new_symbol(open_symbols, self.symbols_allowed, symbol)
                logging.info(f"Can open new position: {can_open_new_position}")

                short_pos_qty = position_data["short"]["qty"]
                long_pos_qty = position_data["long"]["qty"]

                # get liquidation prices
                short_liq_price = position_data["short"]["liq_price"]
                long_liq_price = position_data["long"]["liq_price"]

                self.bybit_reset_position_leverage_long_v3(symbol, long_pos_qty, total_equity, best_ask_price, max_leverage)
                self.bybit_reset_position_leverage_short_v3(symbol, short_pos_qty, total_equity, best_ask_price, max_leverage)

                short_upnl = position_data["short"]["upnl"]
                long_upnl = position_data["long"]["upnl"]

                cum_realised_pnl_long = position_data["long"]["cum_realised"]
                cum_realised_pnl_short = position_data["short"]["cum_realised"]

                short_pos_price = position_data["short"]["price"] if short_pos_qty > 0 else None
                long_pos_price = position_data["long"]["price"] if long_pos_qty > 0 else None

                short_take_profit = None
                long_take_profit = None

                if five_minute_distance != previous_five_minute_distance:
                    short_take_profit = self.calculate_short_take_profit_spread_bybit(short_pos_price, symbol, five_minute_distance)
                    long_take_profit = self.calculate_long_take_profit_spread_bybit(long_pos_price, symbol, five_minute_distance)
                else:
                    if short_take_profit is None or long_take_profit is None:
                        short_take_profit = self.calculate_short_take_profit_spread_bybit(short_pos_price, symbol, five_minute_distance)
                        long_take_profit = self.calculate_long_take_profit_spread_bybit(long_pos_price, symbol, five_minute_distance)
                        
                previous_five_minute_distance = five_minute_distance

                should_short = self.short_trade_condition(best_ask_price, ma_3_high)
                should_long = self.long_trade_condition(best_bid_price, ma_3_low)

                should_add_to_short = False
                should_add_to_long = False
            
                if short_pos_price is not None:
                    should_add_to_short = short_pos_price < ma_6_low and self.short_trade_condition(best_ask_price, ma_6_high)
                    self.short_tp_distance_percent = ((short_take_profit - short_pos_price) / short_pos_price) * 100
                    self.short_expected_profit_usdt = abs(self.short_tp_distance_percent / 100 * short_pos_price * short_pos_qty)
                    logging.info(f"Short TP price: {short_take_profit}, TP distance in percent: {-self.short_tp_distance_percent:.2f}%, Expected profit: {self.short_expected_profit_usdt:.2f} USDT")

                if long_pos_price is not None:
                    should_add_to_long = long_pos_price > ma_6_high and self.long_trade_condition(best_bid_price, ma_6_low)
                    self.long_tp_distance_percent = ((long_take_profit - long_pos_price) / long_pos_price) * 100
                    self.long_expected_profit_usdt = self.long_tp_distance_percent / 100 * long_pos_price * long_pos_qty
                    logging.info(f"Long TP price: {long_take_profit}, TP distance in percent: {self.long_tp_distance_percent:.2f}%, Expected profit: {self.long_expected_profit_usdt:.2f} USDT")
                    
                logging.info(f"Short condition: {should_short}")
                logging.info(f"Long condition: {should_long}")
                logging.info(f"Add short condition: {should_add_to_short}")
                logging.info(f"Add long condition: {should_add_to_long}")

                symbol_data = {
                    'symbol': symbol,
                    'min_qty': min_qty,
                    'current_price': current_price,
                    'balance': total_equity,
                    'available_bal': available_equity,
                    'volume': one_minute_volume,
                    'spread': five_minute_distance,
                    'trend': trend,
                    'long_pos_qty': long_pos_qty,
                    'short_pos_qty': short_pos_qty,
                    'long_upnl': long_upnl,
                    'short_upnl': short_upnl,
                    'long_cum_pnl': cum_realised_pnl_long,
                    'short_cum_pnl': cum_realised_pnl_short,
                    'long_pos_price': long_pos_price,
                    'short_pos_price': short_pos_price
                    # ... continue adding all parameters ...
                }

                ### ILAY ###
                #live.update(self.generate_main_table(symbol_data))
                shared_symbols_data[symbol] = symbol_data
                ### ILAY ###

                if self.config.dashboard_enabled:
                    data_to_save = copy.deepcopy(shared_symbols_data)
                    with open(dashboard_path, "w") as f:
                        json.dump(data_to_save, f)
                    self.update_shared_data(symbol_data, open_position_data, len(open_symbols))

                open_orders = self.retry_api_call(self.exchange.get_open_orders, symbol)

                if trend is not None:
                    if symbol in open_symbols:
                        self.bybit_turbocharged_entry_maker(open_orders, symbol, trend, mfirsi_signal, one_minute_volume, five_minute_distance, min_vol, min_dist, long_take_profit, short_take_profit, long_dynamic_amount, short_dynamic_amount, long_pos_qty, short_pos_qty, long_pos_price, short_pos_price, should_long, should_add_to_long, should_short, should_add_to_short)
                    elif can_open_new_position:  # If the symbol isn't being traded yet and we can open a new position
                        self.bybit_turbocharged_new_entry_maker(open_orders, symbol, trend, mfirsi_signal, one_minute_volume, five_minute_distance, min_vol, min_dist, long_dynamic_amount, short_dynamic_amount)
                else:
                    logging.warning(f"Received invalid trend data for symbol {symbol}. Not placing any trades for this symbol.")
                    
                # Call the function to update long take profit spread
                if long_pos_qty > 0 and long_take_profit is not None:
                    self.bybit_hedge_placetp_maker(symbol, long_pos_qty, long_take_profit, positionIdx=1, order_side="sell", open_orders=open_orders)

                # Call the function to update short take profit spread
                if short_pos_qty > 0 and short_take_profit is not None:
                    self.bybit_hedge_placetp_maker(symbol, short_pos_qty, short_take_profit, positionIdx=2, order_side="buy", open_orders=open_orders)

                # Take profit spread replacement
                if long_pos_qty > 0 and long_take_profit is not None:
                    self.next_long_tp_update = self.update_take_profit_spread_bybit(symbol, long_pos_qty, long_take_profit, positionIdx=1, order_side="sell", open_orders=open_orders, next_tp_update=self.next_long_tp_update)

                if short_pos_qty > 0 and short_take_profit is not None:
                    self.next_short_tp_update = self.update_take_profit_spread_bybit(symbol, short_pos_qty, short_take_profit, positionIdx=2, order_side="buy", open_orders=open_orders, next_tp_update=self.next_short_tp_update)

                # Cancel entries
                self.cancel_entries_bybit(symbol, best_ask_price, ma_1m_3_high, ma_5m_3_high)

                self.cancel_stale_orders_bybit()

                time.sleep(30)
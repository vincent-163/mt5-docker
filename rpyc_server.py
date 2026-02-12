"""rpyc server exposing MetaTrader5 module to Linux clients.

Runs inside Wine Python. Does NOT initialize MT5 at startup —
the client must call initialize(path, login=..., password=..., server=...)
which launches the terminal and connects via IPC.
"""
import os
import re
import glob
import time
import subprocess
import rpyc
import MetaTrader5 as mt5
from rpyc.utils.server import ThreadedServer

INI_PATH = r"C:\Program Files\MetaTrader 5\Config\common.ini"
APPDATA_BASE = os.path.expandvars(r"%APPDATA%\MetaQuotes\Terminal")


def _find_appdata_ini():
    """Find the AppData common.ini dynamically (terminal hash varies by install path)."""
    pattern = os.path.join(APPDATA_BASE, "*", "config", "common.ini")
    matches = glob.glob(pattern)
    return matches[0] if matches else None


def _get_ini_paths():
    """Return all config paths that need updating."""
    paths = [INI_PATH]
    appdata = _find_appdata_ini()
    if appdata:
        paths.append(appdata)
    return paths


def _prepare_ini(login=None, password=None, server=None):
    """Pre-configure common.ini with credentials and re-enable algo trading.

    MT5 resets [Experts] Enabled=0 whenever the account changes.
    By writing the credentials into common.ini BEFORE the terminal starts,
    the terminal sees the same account and doesn't reset the flag.
    """
    for ini_path in _get_ini_paths():
        try:
            with open(ini_path, "r") as f:
                text = f.read()

            if login is not None:
                text = re.sub(r"(?m)^Login=.*", f"Login={login}", text)
            if server is not None:
                text = re.sub(r"(?m)^Server=.*", f"Server={server}", text)

            # Always ensure Experts Enabled=1
            text = re.sub(
                r"(?m)^(\[Experts\].*?^Enabled=)0",
                r"\g<1>1",
                text,
                count=1,
                flags=re.DOTALL,
            )

            with open(ini_path, "w") as f:
                f.write(text)
            print(f"[rpyc] Prepared {ini_path}: Login={login}, Server={server}, Experts=1", flush=True)
        except Exception as e:
            print(f"[rpyc] Warning: could not prepare {ini_path}: {e}", flush=True)


def _delete_accounts_dat():
    """Delete accounts.dat to prevent 'account changed' detection."""
    paths = [
        r"C:\Program Files\MetaTrader 5\Config\accounts.dat",
    ]
    # Also check AppData
    pattern = os.path.join(APPDATA_BASE, "*", "config", "accounts.dat")
    paths.extend(glob.glob(pattern))
    for p in paths:
        try:
            os.remove(p)
            print(f"[rpyc] Deleted {p}", flush=True)
        except FileNotFoundError:
            pass


def _kill_terminal():
    """Kill terminal64.exe processes."""
    try:
        subprocess.run(
            ["taskkill", "/F", "/IM", "terminal64.exe"],
            capture_output=True, timeout=10,
        )
    except Exception:
        pass
    time.sleep(3)


class MT5Service(rpyc.Service):
    ALIASES = ["MT5"]

    def exposed_initialize(self, *args, **kwargs):
        login = kwargs.get("login")
        server = kwargs.get("server")
        if login or server:
            _delete_accounts_dat()
            _prepare_ini(login=login, server=server)

        result = mt5.initialize(*args, **kwargs)
        if result:
            return True

        err = mt5.last_error()
        if err[0] in (-10005, -10003):
            print(f"[rpyc] initialize() failed: {err}, killing terminal and retrying...", flush=True)
            mt5.shutdown()
            _kill_terminal()
            _prepare_ini(login=login, server=server)
            time.sleep(2)
            result = mt5.initialize(*args, **kwargs)
            if result:
                print("[rpyc] Retry succeeded!", flush=True)
                return True
            print(f"[rpyc] Retry also failed: {mt5.last_error()}", flush=True)
        return False

    def exposed_shutdown(self):
        return mt5.shutdown()

    def exposed_login(self, *args, **kwargs):
        return mt5.login(*args, **kwargs)

    def exposed_last_error(self):
        return mt5.last_error()

    def exposed_version(self):
        return mt5.version()

    def exposed_account_info(self):
        info = mt5.account_info()
        if info is None:
            return None
        return info._asdict()

    def exposed_terminal_info(self):
        info = mt5.terminal_info()
        if info is None:
            return None
        return info._asdict()

    def exposed_symbols_total(self):
        return mt5.symbols_total()

    def exposed_symbols_get(self, *args, **kwargs):
        result = mt5.symbols_get(*args, **kwargs)
        if result is None:
            return None
        return [s._asdict() for s in result]

    def exposed_symbol_info(self, symbol):
        info = mt5.symbol_info(symbol)
        if info is None:
            return None
        return info._asdict()

    def exposed_symbol_info_tick(self, symbol):
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            return None
        return tick._asdict()

    def exposed_symbol_select(self, symbol, enable=True):
        return mt5.symbol_select(symbol, enable)

    def exposed_copy_rates_from(self, symbol, timeframe, date_from, count):
        return mt5.copy_rates_from(symbol, timeframe, date_from, count)

    def exposed_copy_rates_from_pos(self, symbol, timeframe, start_pos, count):
        return mt5.copy_rates_from_pos(symbol, timeframe, start_pos, count)

    def exposed_copy_rates_range(self, symbol, timeframe, date_from, date_to):
        return mt5.copy_rates_range(symbol, timeframe, date_from, date_to)

    def exposed_copy_ticks_from(self, symbol, date_from, count, flags):
        return mt5.copy_ticks_from(symbol, date_from, count, flags)

    def exposed_copy_ticks_range(self, symbol, date_from, date_to, flags):
        return mt5.copy_ticks_range(symbol, date_from, date_to, flags)

    def exposed_orders_total(self):
        return mt5.orders_total()

    def exposed_orders_get(self, *args, **kwargs):
        result = mt5.orders_get(*args, **kwargs)
        if result is None:
            return None
        return [o._asdict() for o in result]

    def exposed_positions_total(self):
        return mt5.positions_total()

    def exposed_positions_get(self, *args, **kwargs):
        result = mt5.positions_get(*args, **kwargs)
        if result is None:
            return None
        return [p._asdict() for p in result]

    def exposed_history_orders_total(self, date_from, date_to):
        return mt5.history_orders_total(date_from, date_to)

    def exposed_history_orders_get(self, *args, **kwargs):
        result = mt5.history_orders_get(*args, **kwargs)
        if result is None:
            return None
        return [o._asdict() for o in result]

    def exposed_history_deals_total(self, date_from, date_to):
        return mt5.history_deals_total(date_from, date_to)

    def exposed_history_deals_get(self, *args, **kwargs):
        result = mt5.history_deals_get(*args, **kwargs)
        if result is None:
            return None
        return [d._asdict() for d in result]

    def exposed_order_send(self, request):
        return mt5.order_send(request)._asdict()

    def exposed_order_check(self, request):
        return mt5.order_check(request)._asdict()

    def exposed_order_calc_margin(self, action, symbol, volume, price):
        return mt5.order_calc_margin(action, symbol, volume, price)

    def exposed_order_calc_profit(self, action, symbol, volume, price_open, price_close):
        return mt5.order_calc_profit(action, symbol, volume, price_open, price_close)


if __name__ == "__main__":
    print("Starting rpyc MT5 server on 0.0.0.0:18812...", flush=True)
    server = ThreadedServer(
        MT5Service,
        hostname="0.0.0.0",
        port=18812,
        protocol_config={"allow_public_attrs": True, "sync_request_timeout": 240},
    )
    print("rpyc MT5 server listening on 0.0.0.0:18812", flush=True)
    server.start()

"""HTTP REST server exposing MetaTrader5 module to Linux clients.

Runs inside Wine Python 3.9. Uses only stdlib (http.server + json).
The client must call POST /initialize first to launch the terminal.

Endpoints (all POST, JSON request/response unless noted):
  /initialize     {path, login, password, server}  -> {ok}
  /shutdown       {}                                -> {ok}
  /login          {login, password, server}         -> {ok}
  /last_error     {}                                -> {code, message}
  /version        {}                                -> {version: [...]}
  /account_info   {}                                -> {...}
  /terminal_info  {}                                -> {...}
  /symbols_total  {}                                -> {total}
  /symbols_get    {group?}                          -> [...]
  /symbol_info    {symbol}                          -> {...}
  /symbol_info_tick {symbol}                        -> {...}
  /symbol_select  {symbol, enable?}                 -> {ok}
  /order_send     {request}                         -> {...}
  /order_check    {request}                         -> {...}
  /order_calc_margin  {action, symbol, volume, price} -> {margin}
  /order_calc_profit  {action, symbol, volume, price_open, price_close} -> {profit}
  /orders_total   {}                                -> {total}
  /orders_get     {symbol?, ticket?, group?}        -> [...]
  /positions_total {}                               -> {total}
  /positions_get  {symbol?, ticket?, group?}        -> [...]
  /history_orders_total {date_from, date_to}        -> {total}
  /history_orders_get   {date_from, date_to, ...}   -> [...]
  /history_deals_total  {date_from, date_to}        -> {total}
  /history_deals_get    {date_from, date_to, ...}   -> [...]
  /copy_rates_from      {...} -> numpy binary (application/x-numpy)
  /copy_rates_from_pos  {...} -> numpy binary
  /copy_rates_range     {...} -> numpy binary
  /copy_ticks_from      {...} -> numpy binary
  /copy_ticks_range     {...} -> numpy binary

GET /health -> {ok: true}
"""
import os
import re
import glob
import json
import time
import subprocess
import traceback
from http.server import HTTPServer, BaseHTTPRequestHandler

import MetaTrader5 as mt5

PORT = 18812

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
    """Pre-configure common.ini with credentials and re-enable algo trading."""
    for ini_path in _get_ini_paths():
        try:
            with open(ini_path, "r") as f:
                text = f.read()
            if login is not None:
                text = re.sub(r"(?m)^Login=.*", f"Login={login}", text)
            if server is not None:
                text = re.sub(r"(?m)^Server=.*", f"Server={server}", text)
            text = re.sub(
                r"(?m)^(\[Experts\].*?^Enabled=)0",
                r"\g<1>1", text, count=1, flags=re.DOTALL,
            )
            with open(ini_path, "w") as f:
                f.write(text)
            _log(f"Prepared {ini_path}: Login={login}, Server={server}, Experts=1")
        except Exception as e:
            _log(f"Warning: could not prepare {ini_path}: {e}")


def _delete_accounts_dat():
    """Delete accounts.dat to prevent 'account changed' AutoTrading disable."""
    paths = [r"C:\Program Files\MetaTrader 5\Config\accounts.dat"]
    pattern = os.path.join(APPDATA_BASE, "*", "config", "accounts.dat")
    paths.extend(glob.glob(pattern))
    for p in paths:
        try:
            os.remove(p)
            _log(f"Deleted {p}")
        except FileNotFoundError:
            pass


def _kill_terminal():
    try:
        subprocess.run(["taskkill", "/F", "/IM", "terminal64.exe"],
                       capture_output=True, timeout=10)
    except Exception:
        pass
    time.sleep(3)


def _log(msg):
    print(f"[mt5srv] {msg}", flush=True)


def _namedtuple_list(result):
    if result is None:
        return None
    return [r._asdict() for r in result]


def _parse_datetime(val):
    """Parse a datetime value from JSON (ISO string or unix timestamp)."""
    from datetime import datetime
    if isinstance(val, str):
        return datetime.fromisoformat(val)
    return datetime.utcfromtimestamp(val)


class MT5Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def _read_json(self):
        length = int(self.headers.get("Content-Length", 0))
        if length == 0:
            return {}
        return json.loads(self.rfile.read(length))

    def _send_json(self, data, status=200):
        body = json.dumps(data, default=str).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

    def _send_numpy(self, arr):
        if arr is None:
            self._send_json({"error": True, "last_error": list(mt5.last_error())})
            return
        import io, numpy as np
        buf = io.BytesIO()
        np.save(buf, arr)
        raw = buf.getvalue()
        self.send_response(200)
        self.send_header("Content-Type", "application/x-numpy")
        self.send_header("Content-Length", len(raw))
        self.end_headers()
        self.wfile.write(raw)

    def _send_error(self, msg, status=400):
        self._send_json({"error": True, "message": msg}, status)

    def do_POST(self):
        path = self.path.rstrip("/")
        try:
            body = self._read_json()
        except Exception as e:
            self._send_error(f"Invalid JSON: {e}")
            return
        try:
            handler = ROUTES.get(path)
            if handler is None:
                self._send_error(f"Unknown endpoint: {path}", 404)
                return
            handler(self, body)
        except Exception as e:
            _log(f"Error in {path}: {traceback.format_exc()}")
            self._send_error(f"Internal error: {e}", 500)

    def do_GET(self):
        if self.path == "/health":
            self._send_json({"ok": True})
        else:
            self._send_error("Use POST", 405)


# --- Route handlers ---

def _h_initialize(h, b):
    path = b.get("path", r"C:\Program Files\MetaTrader 5\terminal64.exe")
    login = b.get("login")
    password = b.get("password")
    server = b.get("server")

    if login or server:
        _prepare_ini(login=login, server=server)
    _delete_accounts_dat()

    result = mt5.initialize(path, login=login, password=password, server=server)

    # If initialize succeeded but AutoTrading is disabled (retcode 10027 on
    # order_send), the terminal flagged an "account changed" event from the
    # warmup account.  Fix: shut down, kill terminal, wipe accounts.dat, and
    # reinitialize cleanly so the terminal never sees the old account.
    if result:
        ti = mt5.terminal_info()
        if ti and not ti.trade_allowed:
            _log("AutoTrading disabled after initialize, restarting terminal...")
            mt5.shutdown()
            _kill_terminal()
            _prepare_ini(login=login, server=server)
            _delete_accounts_dat()
            time.sleep(2)
            result = mt5.initialize(path, login=login, password=password, server=server)
            if result:
                ti2 = mt5.terminal_info()
                _log(f"Restart succeeded, trade_allowed={ti2.trade_allowed if ti2 else '?'}")
                h._send_json({"ok": True})
                return
            err = mt5.last_error()
            _log(f"Restart failed: {err}")
            h._send_json({"ok": False, "last_error": list(err)})
            return
        h._send_json({"ok": True})
        return

    err = mt5.last_error()
    if err[0] in (-10005, -10003):
        _log(f"initialize() failed: {err}, killing terminal and retrying...")
        mt5.shutdown()
        _kill_terminal()
        _prepare_ini(login=login, server=server)
        _delete_accounts_dat()
        time.sleep(2)
        result = mt5.initialize(path, login=login, password=password, server=server)
        if result:
            _log("Retry succeeded!")
            h._send_json({"ok": True})
            return
        err = mt5.last_error()
        _log(f"Retry also failed: {err}")

    h._send_json({"ok": False, "last_error": list(err)})


def _h_shutdown(h, b):
    mt5.shutdown()
    h._send_json({"ok": True})


def _h_login(h, b):
    ok = mt5.login(b["login"], password=b.get("password", ""), server=b.get("server", ""))
    if ok:
        h._send_json({"ok": True})
    else:
        h._send_json({"ok": False, "last_error": list(mt5.last_error())})


def _h_last_error(h, b):
    err = mt5.last_error()
    h._send_json({"code": err[0], "message": err[1]})


def _h_version(h, b):
    h._send_json({"version": list(mt5.version())})


def _h_account_info(h, b):
    info = mt5.account_info()
    if info is None:
        h._send_json({"error": True, "last_error": list(mt5.last_error())})
    else:
        h._send_json(info._asdict())


def _h_terminal_info(h, b):
    info = mt5.terminal_info()
    if info is None:
        h._send_json({"error": True, "last_error": list(mt5.last_error())})
    else:
        h._send_json(info._asdict())


def _h_symbols_total(h, b):
    h._send_json({"total": mt5.symbols_total()})


def _h_symbols_get(h, b):
    group = b.get("group")
    result = mt5.symbols_get(group) if group else mt5.symbols_get()
    data = _namedtuple_list(result)
    if data is None:
        h._send_json({"error": True, "last_error": list(mt5.last_error())})
    else:
        h._send_json(data)


def _h_symbol_info(h, b):
    info = mt5.symbol_info(b["symbol"])
    if info is None:
        h._send_json({"error": True, "last_error": list(mt5.last_error())})
    else:
        h._send_json(info._asdict())


def _h_symbol_info_tick(h, b):
    tick = mt5.symbol_info_tick(b["symbol"])
    if tick is None:
        h._send_json({"error": True, "last_error": list(mt5.last_error())})
    else:
        h._send_json(tick._asdict())


def _h_symbol_select(h, b):
    ok = mt5.symbol_select(b["symbol"], b.get("enable", True))
    h._send_json({"ok": ok})


def _h_order_send(h, b):
    request = b.get("request", b)
    result = mt5.order_send(request)
    if result is None:
        h._send_json({"error": True, "last_error": list(mt5.last_error())})
    else:
        h._send_json(result._asdict())


def _h_order_check(h, b):
    request = b.get("request", b)
    result = mt5.order_check(request)
    if result is None:
        h._send_json({"error": True, "last_error": list(mt5.last_error())})
    else:
        h._send_json(result._asdict())


def _h_order_calc_margin(h, b):
    result = mt5.order_calc_margin(b["action"], b["symbol"], b["volume"], b["price"])
    if result is None:
        h._send_json({"error": True, "last_error": list(mt5.last_error())})
    else:
        h._send_json({"margin": result})


def _h_order_calc_profit(h, b):
    result = mt5.order_calc_profit(
        b["action"], b["symbol"], b["volume"], b["price_open"], b["price_close"])
    if result is None:
        h._send_json({"error": True, "last_error": list(mt5.last_error())})
    else:
        h._send_json({"profit": result})


def _h_orders_total(h, b):
    h._send_json({"total": mt5.orders_total()})


def _h_orders_get(h, b):
    kwargs = {k: b[k] for k in ("symbol", "ticket", "group") if k in b}
    result = mt5.orders_get(**kwargs)
    data = _namedtuple_list(result)
    if data is None:
        h._send_json({"error": True, "last_error": list(mt5.last_error())})
    else:
        h._send_json(data)


def _h_positions_total(h, b):
    h._send_json({"total": mt5.positions_total()})


def _h_positions_get(h, b):
    kwargs = {k: b[k] for k in ("symbol", "ticket", "group") if k in b}
    result = mt5.positions_get(**kwargs)
    data = _namedtuple_list(result)
    if data is None:
        h._send_json({"error": True, "last_error": list(mt5.last_error())})
    else:
        h._send_json(data)


def _h_history_orders_total(h, b):
    df, dt = _parse_datetime(b["date_from"]), _parse_datetime(b["date_to"])
    h._send_json({"total": mt5.history_orders_total(df, dt)})


def _h_history_orders_get(h, b):
    df, dt = _parse_datetime(b["date_from"]), _parse_datetime(b["date_to"])
    kwargs = {k: b[k] for k in ("ticket", "group", "position") if k in b}
    result = mt5.history_orders_get(df, dt, **kwargs)
    data = _namedtuple_list(result)
    if data is None:
        h._send_json({"error": True, "last_error": list(mt5.last_error())})
    else:
        h._send_json(data)


def _h_history_deals_total(h, b):
    df, dt = _parse_datetime(b["date_from"]), _parse_datetime(b["date_to"])
    h._send_json({"total": mt5.history_deals_total(df, dt)})


def _h_history_deals_get(h, b):
    df, dt = _parse_datetime(b["date_from"]), _parse_datetime(b["date_to"])
    kwargs = {k: b[k] for k in ("ticket", "group", "position") if k in b}
    result = mt5.history_deals_get(df, dt, **kwargs)
    data = _namedtuple_list(result)
    if data is None:
        h._send_json({"error": True, "last_error": list(mt5.last_error())})
    else:
        h._send_json(data)


# --- Numpy data endpoints ---

def _h_copy_rates_from(h, b):
    result = mt5.copy_rates_from(b["symbol"], b["timeframe"], _parse_datetime(b["date_from"]), b["count"])
    h._send_numpy(result)


def _h_copy_rates_from_pos(h, b):
    result = mt5.copy_rates_from_pos(b["symbol"], b["timeframe"], b["start_pos"], b["count"])
    h._send_numpy(result)


def _h_copy_rates_range(h, b):
    result = mt5.copy_rates_range(b["symbol"], b["timeframe"],
                                  _parse_datetime(b["date_from"]), _parse_datetime(b["date_to"]))
    h._send_numpy(result)


def _h_copy_ticks_from(h, b):
    result = mt5.copy_ticks_from(b["symbol"], _parse_datetime(b["date_from"]), b["count"], b["flags"])
    h._send_numpy(result)


def _h_copy_ticks_range(h, b):
    result = mt5.copy_ticks_range(b["symbol"],
                                  _parse_datetime(b["date_from"]), _parse_datetime(b["date_to"]), b["flags"])
    h._send_numpy(result)


ROUTES = {
    "/initialize": _h_initialize,
    "/shutdown": _h_shutdown,
    "/login": _h_login,
    "/last_error": _h_last_error,
    "/version": _h_version,
    "/account_info": _h_account_info,
    "/terminal_info": _h_terminal_info,
    "/symbols_total": _h_symbols_total,
    "/symbols_get": _h_symbols_get,
    "/symbol_info": _h_symbol_info,
    "/symbol_info_tick": _h_symbol_info_tick,
    "/symbol_select": _h_symbol_select,
    "/order_send": _h_order_send,
    "/order_check": _h_order_check,
    "/order_calc_margin": _h_order_calc_margin,
    "/order_calc_profit": _h_order_calc_profit,
    "/orders_total": _h_orders_total,
    "/orders_get": _h_orders_get,
    "/positions_total": _h_positions_total,
    "/positions_get": _h_positions_get,
    "/history_orders_total": _h_history_orders_total,
    "/history_orders_get": _h_history_orders_get,
    "/history_deals_total": _h_history_deals_total,
    "/history_deals_get": _h_history_deals_get,
    "/copy_rates_from": _h_copy_rates_from,
    "/copy_rates_from_pos": _h_copy_rates_from_pos,
    "/copy_rates_range": _h_copy_rates_range,
    "/copy_ticks_from": _h_copy_ticks_from,
    "/copy_ticks_range": _h_copy_ticks_range,
}


if __name__ == "__main__":
    _log(f"Starting MT5 HTTP server on 0.0.0.0:{PORT}...")
    server = HTTPServer(("0.0.0.0", PORT), MT5Handler)
    _log(f"MT5 HTTP server listening on 0.0.0.0:{PORT}")
    server.serve_forever()

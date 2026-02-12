"""Connect to MT5 rpyc server running in Docker and check account info.

Usage:
    python mt5_client.py <LOGIN> <PASSWORD> <SERVER>

Example:
    python mt5_client.py 12345678 'mypassword' '1.2.3.4:443'
"""
import sys
import rpyc

RPYC_HOST = "127.0.0.1"
RPYC_PORT = 18812

MT5_PATH = r"C:\Program Files\MetaTrader 5\terminal64.exe"

if len(sys.argv) < 4:
    print("Usage: python mt5_client.py <LOGIN> <PASSWORD> <SERVER>")
    raise SystemExit(1)

LOGIN = int(sys.argv[1])
PASSWORD = sys.argv[2]
SERVER = sys.argv[3]

print(f"Connecting to rpyc server at {RPYC_HOST}:{RPYC_PORT}...")
conn = rpyc.connect(RPYC_HOST, RPYC_PORT, config={"allow_public_attrs": True, "sync_request_timeout": 240})
mt5 = conn.root

print(f"Initializing MT5 (login={LOGIN}, server={SERVER})...")
result = mt5.initialize(MT5_PATH, login=LOGIN, password=PASSWORD, server=SERVER)
if not result:
    err = mt5.last_error()
    print(f"initialize() failed: {err}")
    if err[0] == -6:
        print("Terminal connected but auth failed, trying login()...")
        if not mt5.login(LOGIN, password=PASSWORD, server=SERVER):
            print(f"login() failed: {mt5.last_error()}")
            mt5.shutdown()
            raise SystemExit(1)
        print("login() succeeded!")
    else:
        mt5.shutdown()
        raise SystemExit(1)
else:
    print("initialize() succeeded!")

print(f"MT5 version: {mt5.version()}")

info = mt5.account_info()
if info is None:
    print(f"account_info() failed: {mt5.last_error()}")
else:
    print(f"Account: {info['login']}")
    print(f"Server:  {info['server']}")
    print(f"Balance: {info['balance']}")
    print(f"Equity:  {info['equity']}")
    print(f"Currency: {info['currency']}")

print(f"Total symbols: {mt5.symbols_total()}")

mt5.shutdown()
conn.close()
print("Done.")

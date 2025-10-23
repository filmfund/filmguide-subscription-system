import os
import json
import time
from typing import List, Optional

from fastapi import FastAPI
from pydantic import BaseModel
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from web3 import Web3
from web3.middleware import geth_poa_middleware
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

SEPOLIA_RPC_URL = os.getenv('SEPOLIA_RPC_URL')
PRIVATE_KEY = os.getenv('PRIVATE_KEY')
CONTRACT_ADDRESS = os.getenv('CONTRACT_ADDRESS')
START_BLOCK = int(os.getenv('START_BLOCK', '0'))
POLL_INTERVAL_SECONDS = int(os.getenv('POLL_INTERVAL_SECONDS', '300'))

if not (SEPOLIA_RPC_URL and PRIVATE_KEY and CONTRACT_ADDRESS):
    print('[WARN] Missing environment variables. Please set SEPOLIA_RPC_URL, PRIVATE_KEY, CONTRACT_ADDRESS')

# Web3 setup
w3 = Web3(Web3.HTTPProvider(SEPOLIA_RPC_URL)) if SEPOLIA_RPC_URL else None
if w3 is not None and 'sepolia' in (SEPOLIA_RPC_URL or '').lower():
    # Some Sepolia endpoints require POA middleware
    try:
        w3.middleware_onion.inject(geth_poa_middleware, layer=0)
    except Exception:
        pass

account = w3.eth.account.from_key(PRIVATE_KEY) if (w3 and PRIVATE_KEY) else None

# Load ABI
ABI_PATH = os.path.join(os.path.dirname(__file__), 'abi.json')
with open(ABI_PATH, 'r') as f:
    CONTRACT_ABI = json.load(f)

contract = w3.eth.contract(address=Web3.to_checksum_address(CONTRACT_ADDRESS), abi=CONTRACT_ABI) if (w3 and CONTRACT_ADDRESS) else None

# In-memory index of known subscription IDs
known_subscription_ids: set[int] = set()
last_scanned_block: int = START_BLOCK

app = FastAPI(title='GUIDE2FILM3 Subscription Backend', version='0.1.0')


class ScanResult(BaseModel):
    addedSubscriptions: List[int]
    processedPayments: List[int]


def get_current_block() -> int:
    return int(w3.eth.block_number) if w3 else 0


def fetch_new_subscriptions(from_block: int, to_block: int) -> List[int]:
    if not contract:
        return []
    event = contract.events.SubscriptionCreated
    try:
        logs = event().get_logs(fromBlock=from_block, toBlock=to_block)
    except Exception as e:
        print(f"[ERROR] fetching logs: {e}")
        return []

    new_ids: List[int] = []
    for log in logs:
        sub_id = int(log['args']['subscriptionId'])
        if sub_id not in known_subscription_ids:
            known_subscription_ids.add(sub_id)
            new_ids.append(sub_id)
    return new_ids


def is_due(subscription_id: int) -> bool:
    try:
        sub = contract.functions.getSubscription(subscription_id).call()
        active = bool(sub[4])
        next_payment = int(sub[3])
        now_ts = int(time.time())
        return active and now_ts >= next_payment
    except Exception as e:
        print(f"[ERROR] reading subscription {subscription_id}: {e}")
        return False


def process_payment(subscription_id: int) -> Optional[str]:
    try:
        nonce = w3.eth.get_transaction_count(account.address)
        tx = contract.functions.processPayment(subscription_id).build_transaction({
            'from': account.address,
            'nonce': nonce,
            'gas': 300_000,
            'maxFeePerGas': w3.to_wei('2', 'gwei'),
            'maxPriorityFeePerGas': w3.to_wei('1', 'gwei')
        })
        signed = w3.eth.account.sign_transaction(tx, private_key=PRIVATE_KEY)
        tx_hash = w3.eth.send_raw_transaction(signed.rawTransaction)
        print(f"[TX] processPayment({subscription_id}) -> {tx_hash.hex()}")
        return tx_hash.hex()
    except Exception as e:
        print(f"[ERROR] processing payment for {subscription_id}: {e}")
        return None


def scan_and_process() -> ScanResult:
    global last_scanned_block
    if not w3 or not contract or not account:
        print('[WARN] Web3/contract/account not configured')
        return ScanResult(addedSubscriptions=[], processedPayments=[])

    current_block = get_current_block()
    from_block = last_scanned_block or (current_block - 2_000)
    to_block = current_block

    added = fetch_new_subscriptions(from_block, to_block)

    processed: List[int] = []
    # Check all known subscriptions for due payments
    for sub_id in list(known_subscription_ids):
        if is_due(sub_id):
            tx_hash = process_payment(sub_id)
            if tx_hash:
                processed.append(sub_id)

    last_scanned_block = to_block
    return ScanResult(addedSubscriptions=added, processedPayments=processed)


@app.get('/health')
def health():
    return { 'status': 'ok', 'knownSubscriptions': len(known_subscription_ids), 'lastScannedBlock': last_scanned_block }


@app.post('/scan', response_model=ScanResult)
def scan():
    return scan_and_process()


@app.post('/process/{subscription_id}')
def process(subscription_id: int):
    if not is_due(subscription_id):
        return { 'status': 'not_due' }
    tx = process_payment(subscription_id)
    return { 'status': 'submitted' if tx else 'error', 'txHash': tx }


# Background scheduler
scheduler = BackgroundScheduler()

@app.on_event('startup')
def on_startup():
    # Initial backfill from START_BLOCK to current
    try:
        current = get_current_block()
        _ = fetch_new_subscriptions(START_BLOCK or max(0, current - 5_000), current)
    except Exception as e:
        print(f"[WARN] initial backfill failed: {e}")

    if POLL_INTERVAL_SECONDS > 0:
        scheduler.add_job(scan_and_process, IntervalTrigger(seconds=POLL_INTERVAL_SECONDS))
        scheduler.start()
        print(f"[INFO] Scheduler started; interval={POLL_INTERVAL_SECONDS}s")

@app.on_event('shutdown')
def on_shutdown():
    try:
        scheduler.shutdown(wait=False)
    except Exception:
        pass

#!/usr/bin/env python3
"""
Minimal Ethereum wallet for Hermit agents.

Usage (via uv):
    uv run --with web3 wallet.py balance
    uv run --with web3 wallet.py send <to_address> <amount_eth>
    uv run --with web3 wallet.py address

Supports Base mainnet and Base Sepolia testnet.
Private key stored in /workspace/.secrets/wallet.key (hex, no 0x prefix).
"""

import json
import os
import sys
from pathlib import Path

# Lazy import web3 to allow --help without dependencies
def get_web3():
    from web3 import Web3
    return Web3

# Configuration
NETWORKS = {
    "base": {
        "rpc": "https://mainnet.base.org",
        "chain_id": 8453,
        "explorer": "https://basescan.org",
    },
    "base-sepolia": {
        "rpc": "https://sepolia.base.org",
        "chain_id": 84532,
        "explorer": "https://sepolia.basescan.org",
    },
}

DEFAULT_NETWORK = "base-sepolia"  # Start on testnet
SECRETS_DIR = Path("/workspace/.secrets")
KEY_FILE = SECRETS_DIR / "wallet.key"


def load_private_key() -> str:
    """Load private key from file."""
    if not KEY_FILE.exists():
        print(f"Error: No private key found at {KEY_FILE}")
        print("Generate one with: wallet.py generate")
        sys.exit(1)

    key = KEY_FILE.read_text().strip()
    if key.startswith("0x"):
        key = key[2:]
    return key


def save_private_key(key: str):
    """Save private key to file with restricted permissions."""
    SECRETS_DIR.mkdir(parents=True, exist_ok=True)
    KEY_FILE.write_text(key)
    KEY_FILE.chmod(0o600)


def get_web3_and_account(network: str = DEFAULT_NETWORK):
    """Initialize Web3 and account."""
    Web3 = get_web3()

    if network not in NETWORKS:
        print(f"Error: Unknown network '{network}'. Available: {list(NETWORKS.keys())}")
        sys.exit(1)

    config = NETWORKS[network]
    w3 = Web3(Web3.HTTPProvider(config["rpc"]))

    if not w3.is_connected():
        print(f"Error: Could not connect to {config['rpc']}")
        sys.exit(1)

    key = load_private_key()
    account = w3.eth.account.from_key(key)

    return w3, account, config


def cmd_generate():
    """Generate a new wallet."""
    if KEY_FILE.exists():
        print(f"Error: Key already exists at {KEY_FILE}")
        print("Delete it first if you want to generate a new one.")
        sys.exit(1)

    Web3 = get_web3()
    account = Web3().eth.account.create()
    save_private_key(account.key.hex())

    print(f"Generated new wallet!")
    print(f"Address: {account.address}")
    print(f"Private key saved to: {KEY_FILE}")
    print()
    print("IMPORTANT: Back up your private key. If lost, funds are unrecoverable.")
    print(f"Get testnet ETH: https://www.alchemy.com/faucets/base-sepolia")


def cmd_address(network: str = DEFAULT_NETWORK):
    """Show wallet address."""
    w3, account, config = get_web3_and_account(network)
    print(f"Address: {account.address}")
    print(f"Explorer: {config['explorer']}/address/{account.address}")


def cmd_balance(network: str = DEFAULT_NETWORK):
    """Check wallet balance."""
    w3, account, config = get_web3_and_account(network)

    balance_wei = w3.eth.get_balance(account.address)
    balance_eth = w3.from_wei(balance_wei, "ether")

    print(f"Network: {network}")
    print(f"Address: {account.address}")
    print(f"Balance: {balance_eth} ETH")


def cmd_send(to_address: str, amount_eth: str, network: str = DEFAULT_NETWORK):
    """Send ETH to an address."""
    w3, account, config = get_web3_and_account(network)

    # Validate address
    if not w3.is_address(to_address):
        print(f"Error: Invalid address '{to_address}'")
        sys.exit(1)

    to_address = w3.to_checksum_address(to_address)
    amount_wei = w3.to_wei(float(amount_eth), "ether")

    # Check balance
    balance = w3.eth.get_balance(account.address)
    if balance < amount_wei:
        print(f"Error: Insufficient balance. Have {w3.from_wei(balance, 'ether')} ETH, need {amount_eth} ETH")
        sys.exit(1)

    # Build transaction
    nonce = w3.eth.get_transaction_count(account.address)
    gas_price = w3.eth.gas_price

    tx = {
        "nonce": nonce,
        "to": to_address,
        "value": amount_wei,
        "gas": 21000,  # Standard ETH transfer
        "gasPrice": gas_price,
        "chainId": config["chain_id"],
    }

    # Estimate total cost
    total_cost = amount_wei + (21000 * gas_price)
    if balance < total_cost:
        print(f"Error: Insufficient balance for tx + gas")
        sys.exit(1)

    # Sign and send
    signed = w3.eth.account.sign_transaction(tx, account.key)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)

    print(f"Transaction sent!")
    print(f"To: {to_address}")
    print(f"Amount: {amount_eth} ETH")
    print(f"TX Hash: {tx_hash.hex()}")
    print(f"Explorer: {config['explorer']}/tx/{tx_hash.hex()}")

    # Wait for confirmation
    print("Waiting for confirmation...")
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)

    if receipt["status"] == 1:
        print(f"Confirmed in block {receipt['blockNumber']}")
    else:
        print("Transaction failed!")
        sys.exit(1)


def cmd_help():
    """Show help."""
    print(__doc__)
    print("Commands:")
    print("  generate              Generate a new wallet")
    print("  address [--network]   Show wallet address")
    print("  balance [--network]   Check balance")
    print("  send <to> <amount>    Send ETH")
    print()
    print("Networks: base, base-sepolia (default)")


def main():
    args = sys.argv[1:]

    if not args or args[0] in ("-h", "--help", "help"):
        cmd_help()
        return

    cmd = args[0]

    # Parse --network flag
    network = DEFAULT_NETWORK
    if "--network" in args:
        idx = args.index("--network")
        if idx + 1 < len(args):
            network = args[idx + 1]
            args = args[:idx] + args[idx+2:]

    if cmd == "generate":
        cmd_generate()
    elif cmd == "address":
        cmd_address(network)
    elif cmd == "balance":
        cmd_balance(network)
    elif cmd == "send":
        if len(args) < 3:
            print("Usage: wallet.py send <to_address> <amount_eth>")
            sys.exit(1)
        cmd_send(args[1], args[2], network)
    else:
        print(f"Unknown command: {cmd}")
        cmd_help()
        sys.exit(1)


if __name__ == "__main__":
    main()

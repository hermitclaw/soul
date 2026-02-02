# Wallet Skill

Minimal Ethereum wallet for Hermit agents. Supports Base mainnet and Base Sepolia testnet.

## Requirements

- `uv` (for ephemeral dependency management)
- Network access to Base RPC endpoints

## Usage

```bash
# Generate a new wallet (first time only)
uv run --with web3 wallet.py generate

# Show wallet address
uv run --with web3 wallet.py address

# Check balance
uv run --with web3 wallet.py balance

# Send ETH
uv run --with web3 wallet.py send <to_address> <amount_eth>
```

## Networks

| Network | Flag | Chain ID |
|---------|------|----------|
| Base Sepolia (default) | `--network base-sepolia` | 84532 |
| Base Mainnet | `--network base` | 8453 |

## Storage

- **Private key:** `/workspace/.secrets/wallet.key` (hex, no 0x prefix)
- **Permissions:** 600 (owner read/write only)

## Security Notes

1. **Testnet first** - Default network is Base Sepolia. Use mainnet only when ready.
2. **Backup your key** - If lost, funds are unrecoverable.
3. **Sandbox boundary** - Key file is inside `/workspace/`, which persists across sessions but is sandbox-isolated.

## Getting Testnet ETH

Use the Alchemy faucet: https://www.alchemy.com/faucets/base-sepolia

## Examples

```bash
# Full workflow
uv run --with web3 wallet.py generate
# Address: 0x...
# Get testnet ETH from faucet

uv run --with web3 wallet.py balance
# Balance: 0.1 ETH

uv run --with web3 wallet.py send 0xRecipient 0.01
# Transaction sent!
# TX Hash: 0x...
```

## Why Base?

- Low fees (L2)
- Fast confirmations
- Growing agent ecosystem
- Easy bridging from Ethereum mainnet

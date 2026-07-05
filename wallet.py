"""
The marketplace's single escrow wallet.

Every buyer pays into their own order's unique address, but all of those
addresses belong to this one wallet, which is the thing actually holding
custody of funds (this is the "site wallet" you asked for). The private
key behind it lives only in your .env file (ESCROW_XPRV) -- see config.py
and init_wallet.py.

Nothing here relies on any paid service. bitcoinlib's built-in service
layer talks to free public block explorers to check balances and
broadcast transactions.
"""

from bitcoinlib.wallets import Wallet, wallet_delete_if_exists, WalletError
from bitcoinlib.services.services import ServiceError
from flask import current_app

SATS_PER_BTC = 100_000_000


def get_wallet():
    """
    Loads the marketplace's one and only escrow wallet, creating it in
    the local wallet database on first run from ESCROW_XPRV.
    """
    name = current_app.config["WALLET_NAME"]
    try:
        return Wallet(name)
    except WalletError:
        xprv = current_app.config["ESCROW_XPRV"]
        if not xprv or "paste" in xprv or "here" in xprv:
            raise RuntimeError(
                "ESCROW_XPRV in your .env file isn't set to a real key yet. "
                "Run `python init_wallet.py --network testnet4`, then copy "
                "the ESCROW_XPRV= line it prints into your .env file, "
                "replacing the placeholder text."
            )
        return Wallet.create(
            name,
            keys=xprv,
            network=current_app.config["BTC_NETWORK"],
            witness_type="segwit",
        )


def new_deposit_address():
    """
    Returns (address, key_id) for a brand new order. Every order gets its
    own never-reused address, so payments and payouts for one order can't
    get mixed up with any other order's funds.
    """
    w = get_wallet()
    key = w.new_key()
    return key.address, key.key_id


def check_payment(key_id: int, required_confirmations: int):
    """
    Refreshes this address's data from the network and returns:
        {"received_btc": float, "confirmations": int, "txid": str or None}

    The free public block explorers behind this occasionally time out or
    rate-limit -- that's normal and not a bug in your app, so a failed
    check here just reports "nothing new yet" instead of crashing the
    order page. The next page load/refresh tries again.
    """
    w = get_wallet()
    try:
        w.utxos_update(key_id=key_id)
    except ServiceError:
        return {"received_btc": 0.0, "confirmations": 0, "txid": None, "is_final": False, "check_failed": True}

    utxos = w.utxos(key_id=key_id)

    if not utxos:
        return {"received_btc": 0.0, "confirmations": 0, "txid": None, "is_final": False}

    total_sats = sum(u["value"] for u in utxos)
    min_confirmations = min(u["confirmations"] for u in utxos)
    txid = utxos[0]["txid"]

    return {
        "received_btc": total_sats / SATS_PER_BTC,
        "confirmations": min_confirmations,
        "txid": txid,
        "is_final": min_confirmations >= required_confirmations,
    }


def release_to_seller(order, commission_percent: float):
    """
    Pays the seller out of THIS order's escrowed funds only (input_key_id
    restricts spending to that one address's UTXOs -- it is not possible
    for this call to accidentally touch any other order's money).

    The commission is not moved anywhere separately -- it's simply the
    change left over from this transaction, which bitcoinlib sends back
    to a fresh address inside this same wallet automatically. That's the
    marketplace's cut, already in the site wallet, no extra step needed.

    Returns (payout_txid, commission_btc_kept).
    """
    w = get_wallet()
    w.utxos_update(key_id=order.wallet_key_id)

    total_sats = int(order.expected_amount_btc * SATS_PER_BTC)
    seller_sats = int(total_sats * (1 - commission_percent / 100))

    tx = w.send_to(
        order.product.seller_payout_address,
        seller_sats,
        input_key_id=order.wallet_key_id,
        broadcast=True,
    )

    commission_btc = (total_sats - seller_sats - tx.fee) / SATS_PER_BTC
    return tx.txid, max(commission_btc, 0.0)


def refund_to_buyer(order):
    """
    Sends everything escrowed for this order back to the buyer's own
    refund address, again restricted to only that order's funds.
    """
    w = get_wallet()
    w.utxos_update(key_id=order.wallet_key_id)

    utxo_total_sats = sum(u["value"] for u in w.utxos(key_id=order.wallet_key_id))
    if utxo_total_sats <= 0:
        raise RuntimeError("Nothing escrowed for this order yet -- nothing to refund.")

    tx = w.sweep(
        order.buyer_refund_address,
        account_id=None,
        input_key_id=order.wallet_key_id,
        broadcast=True,
    )
    return tx.txid


def reset_wallet_dev_only():
    """Dev helper: wipes local wallet cache. Never call this in production."""
    wallet_delete_if_exists(current_app.config["WALLET_NAME"], force=True)

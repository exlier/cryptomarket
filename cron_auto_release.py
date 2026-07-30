#!/usr/bin/env python3
import os, sys
from datetime import datetime, timedelta
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from app import app, db
from models import Order, Ledger, WalletConfig

def run():
    with app.app_context():
        limit = datetime.utcnow() - timedelta(days=14)
        orders = Order.query.filter(
            Order.escrow_state.in_(['Paid & Awaiting Fulfillment', 'Dispatched / In Transit']),
            Order.dispatched_at != None,
            Order.dispatched_at <= limit
        ).all()
        for order in orders:
            try:
                wallet = WalletConfig.query.filter_by(currency='BTC').first()
                fee = wallet.platform_fee_percentage if wallet else 0.05
                comm = round(order.amount_crypto * fee, 8)
                db.session.add(Ledger(vendor_id=order.vendor_id, order_id=order.id,
                                      gross_amount=order.amount_crypto, platform_fee=comm,
                                      net_payout=round(order.amount_crypto - comm, 8), is_paid_out=False))
                order.escrow_state = 'Delivered & Released'
                db.session.commit()
                print(f"Released order {order.id}")
            except Exception as e:
                db.session.rollback()
                print(f"Failed order {order.id}: {e}")

if __name__ == '__main__':
    run()

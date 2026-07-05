import base64
import io
import os

import qrcode
from flask import Flask, render_template, request, redirect, url_for, flash
from datetime import datetime

from config import Config
from models import db, Product, Order
import wallet as escrow_wallet


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    os.makedirs(app.instance_path, exist_ok=True)
    if not app.config["SQLALCHEMY_DATABASE_URI"]:
        db_path = os.path.join(app.instance_path, "marketplace.db")
        app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{db_path}"
    db.init_app(app)

    with app.app_context():
        db.create_all()
        _seed_demo_products()

    register_routes(app)
    return app


def _seed_demo_products():
    if Product.query.count() > 0:
        return
    demo = [
        Product(
            title="Mechanical keyboard, hot-swappable switches",
            description="75% layout, hot-swap sockets, USB-C.",
            price_btc=0.0021,
            seller_name="northline_gear",
            seller_payout_address="tb1qexampleseller0000000000000000000000",
            category="electronics",
        ),
        Product(
            title="Hand-poured soy candle, cedar & fig",
            description="40 hour burn time, cotton wick.",
            price_btc=0.00035,
            seller_name="wick_and_wood",
            seller_payout_address="tb1qexampleseller1111111111111111111111",
            category="home",
        ),
        Product(
            title="Vintage film camera, fully serviced",
            description="35mm, recently CLA'd, light seals replaced.",
            price_btc=0.0064,
            seller_name="silverhalide",
            seller_payout_address="tb1qexampleseller2222222222222222222222",
            category="electronics",
        ),
    ]
    db.session.add_all(demo)
    db.session.commit()


def qr_data_uri(data: str) -> str:
    img = qrcode.make(data)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    encoded = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def register_routes(app):

    @app.route("/")
    def index():
        products = Product.query.all()
        return render_template("index.html", products=products)

    @app.route("/product/<int:product_id>")
    def product_detail(product_id):
        product = Product.query.get_or_404(product_id)
        return render_template("product.html", product=product)

    @app.route("/checkout/<int:product_id>", methods=["GET", "POST"])
    def checkout(product_id):
        product = Product.query.get_or_404(product_id)

        if request.method == "POST":
            buyer_contact = request.form["buyer_contact"].strip()
            buyer_refund_address = request.form["buyer_refund_address"].strip()

            if not buyer_contact or not buyer_refund_address:
                flash("Please fill in both fields.", "error")
                return render_template("checkout.html", product=product)

            address, key_id = escrow_wallet.new_deposit_address()

            order = Order(
                product_id=product.id,
                buyer_contact=buyer_contact,
                buyer_refund_address=buyer_refund_address,
                deposit_address=address,
                wallet_key_id=key_id,
                expected_amount_btc=product.price_btc,
            )
            db.session.add(order)
            db.session.commit()

            return redirect(url_for("order_status", order_id=order.id))

        return render_template("checkout.html", product=product)

    @app.route("/order/<int:order_id>")
    def order_status(order_id):
        order = Order.query.get_or_404(order_id)

        check_failed = False
        if order.status == "awaiting_payment":
            result = escrow_wallet.check_payment(
                order.wallet_key_id, app.config["REQUIRED_CONFIRMATIONS"]
            )
            check_failed = result.get("check_failed", False)
            order.received_amount_btc = result["received_btc"]
            if result["txid"]:
                order.incoming_txid = result["txid"]
            if result.get("is_final") and result["received_btc"] >= order.expected_amount_btc:
                order.status = "escrowed"
                order.escrowed_at = datetime.utcnow()
            db.session.commit()

        payment_uri = f"bitcoin:{order.deposit_address}?amount={order.expected_amount_btc}"
        qr = qr_data_uri(payment_uri)
        return render_template("order_status.html", order=order, qr=qr, check_failed=check_failed)

    @app.route("/admin")
    def admin_orders():
        orders = Order.query.order_by(Order.created_at.desc()).all()
        return render_template("admin_orders.html", orders=orders)

    @app.route("/admin/order/<int:order_id>/release", methods=["POST"])
    def admin_release(order_id):
        order = Order.query.get_or_404(order_id)
        if order.status != "escrowed":
            flash("Order isn't in escrow, nothing to release.", "error")
            return redirect(url_for("admin_orders"))

        txid, commission = escrow_wallet.release_to_seller(
            order, app.config["COMMISSION_PERCENT"]
        )
        order.status = "released"
        order.payout_txid = txid
        order.commission_btc = commission
        order.released_at = datetime.utcnow()
        db.session.commit()
        flash(f"Released to seller. Payout tx: {txid}", "success")
        return redirect(url_for("admin_orders"))

    @app.route("/admin/order/<int:order_id>/refund", methods=["POST"])
    def admin_refund(order_id):
        order = Order.query.get_or_404(order_id)
        if order.status not in ("escrowed", "disputed"):
            flash("Nothing escrowed for this order to refund.", "error")
            return redirect(url_for("admin_orders"))

        txid = escrow_wallet.refund_to_buyer(order)
        order.status = "refunded"
        order.payout_txid = txid
        order.released_at = datetime.utcnow()
        db.session.commit()
        flash(f"Refunded to buyer. Tx: {txid}", "success")
        return redirect(url_for("admin_orders"))

    @app.route("/admin/order/<int:order_id>/dispute", methods=["POST"])
    def admin_dispute(order_id):
        order = Order.query.get_or_404(order_id)
        order.status = "disputed"
        order.dispute_note = request.form.get("note", "")
        db.session.commit()
        flash("Order marked as disputed.", "success")
        return redirect(url_for("admin_orders"))


app = create_app()

if __name__ == "__main__":
    app.run(debug=True, port=5000)

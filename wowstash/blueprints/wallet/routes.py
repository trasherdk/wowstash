import subprocess
from io import BytesIO
from base64 import b64encode
from qrcode import make as qrcode_make
from decimal import Decimal
from flask import request, render_template, session, jsonify
from flask import redirect, url_for, current_app, flash
from flask_login import login_required, current_user
from socket import socket
from datetime import datetime
from wowstash.blueprints.wallet import wallet_bp
from wowstash.library.jsonrpc import Wallet, to_atomic
from wowstash.library.cache import cache
from wowstash.forms import Send
from wowstash.factory import db
from wowstash.models import User
from wowstash import config


@wallet_bp.route('/wallet/loading')
@login_required
def loading():
    if current_user.wallet_connected and current_user.wallet_created:
        return redirect(url_for('wallet.dashboard'))
    return render_template('wallet/loading.html')

@wallet_bp.route('/wallet/dashboard')
@login_required
def dashboard():
    send_form = Send()
    _address_qr = BytesIO()
    all_transfers = list()
    wallet = Wallet(
        proto='http',
        host='127.0.0.1',
        port=current_user.wallet_port,
        username=current_user.id,
        password=current_user.wallet_password
    )
    if not wallet.connected:
        return redirect(url_for('wallet.loading'))

    address = wallet.get_address()
    transfers = wallet.get_transfers()
    for type in transfers:
        for tx in transfers[type]:
            all_transfers.append(tx)
    balances = wallet.get_balances()
    qr_uri = f'wownero:{address}?tx_description="{current_user.email}"'
    address_qr = qrcode_make(qr_uri).save(_address_qr)
    qrcode = b64encode(_address_qr.getvalue()).decode()
    return render_template(
        'wallet/dashboard.html',
        transfers=all_transfers,
        balances=balances,
        address=address,
        qrcode=qrcode,
        send_form=send_form,
        user=current_user
    )

@wallet_bp.route('/wallet/connect')
@login_required
def connect():
    if current_user.wallet_connected is False:
        tcp = socket()
        tcp.bind(('', 0))
        _, port = tcp.getsockname()
        tcp.close()
        command = f"""wownero-wallet-rpc \
        --detach \
        --non-interactive \
        --rpc-bind-port {port} \
        --wallet-file {config.WALLET_DIR}/{current_user.id}.wallet \
        --rpc-login {current_user.id}:{current_user.wallet_password} \
        --password {current_user.wallet_password} \
        --daemon-address {config.DAEMON_PROTO}://{config.DAEMON_HOST}:{config.DAEMON_PORT} \
        --daemon-login {config.DAEMON_USER}:{config.DAEMON_PASS} \
        --log-file {config.WALLET_DIR}/{current_user.id}.log
        """
        proc = subprocess.Popen(command.split(), stdout=subprocess.PIPE)
        outs, errs = proc.communicate()
        # print(outs)
        if proc.returncode == 0:
            print(f'Successfully started RPC for {current_user}!')
            current_user.wallet_connected = True
            current_user.wallet_port = port
            current_user.wallet_pid = proc.pid
            current_user.wallet_connect_date = datetime.now()
            db.session.commit()

    return "ok"

@wallet_bp.route('/wallet/status')
@login_required
def status():
    data = {
        "created": current_user.wallet_created,
        "connected": current_user.wallet_connected,
        "port": current_user.wallet_port,
        "date": current_user.wallet_connect_date
    }
    return jsonify(data)

@wallet_bp.route('/wallet/send', methods=['GET', 'POST'])
@login_required
def send():
    send_form = Send()
    redirect_url = url_for('wallet.dashboard') + '#send'
    if send_form.validate_on_submit():
        address = str(send_form.address.data)
        user = User.query.get(current_user.id)

        # Check if Wownero wallet is available
        if wallet.connected is False:
            flash('Wallet RPC interface is unavailable at this time. Try again later.')
            return redirect(redirect_url)

        # Check if user funds flag is locked
        if current_user.funds_locked:
            flash('You currently have transactions pending and transfers are locked. Try again later.')
            return redirect(redirect_url)

        # Quick n dirty check to see if address is WOW
        if len(address) not in [97, 108]:
            flash('Invalid Wownero address provided.')
            return redirect(redirect_url)

        # Make sure the amount provided is a number
        try:
            amount = to_atomic(Decimal(send_form.amount.data))
        except:
            flash('Invalid Wownero amount specified.')
            return redirect(redirect_url)

        # Make sure the amount does not exceed the balance
        if amount >= user.balance:
            flash('Not enough funds to transfer that much.')
            return redirect(redirect_url)

        # Lock user funds
        user.funds_locked = True
        db.session.commit()

        # Queue the transaction
        tx = TransferQueue(
            user=user.id,
            address=address,
            amount=amount
        )
        db.session.add(tx)
        db.session.commit()

        # Redirect back
        flash('Successfully queued transfer.')
        return redirect(redirect_url)
    else:
        for field, errors in send_form.errors.items():
            flash(f'{send_form[field].label}: {", ".join(errors)}')
        return redirect(redirect_url)

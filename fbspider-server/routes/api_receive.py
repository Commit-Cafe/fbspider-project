from flask import Blueprint, request, jsonify
import json
from auth import get_current_user
from models import (upsert_ad_account, upsert_bm, upsert_bm_ad_account,
                     upsert_ad_account_user, upsert_pixel, upsert_pixel_association,
                     save_pixel_purchases, upsert_ad_library_item, set_extension_state,
                     add_action_log, upsert_campaign, update_account_dsl_status)

# Currency offset mapping — matches background.js currencySymbols.offset values.
# offset=1: API returns base units (no division needed)
# offset=5: divide by 5
# offset=100 (default): divide by 100
CURRENCY_OFFSETS = {
    'BIF': 1, 'CLP': 1, 'COP': 1, 'CRC': 1, 'CVE': 1, 'DJF': 1,
    'GNF': 1, 'HUF': 1, 'IDR': 1, 'ISK': 1, 'JPY': 1, 'KMF': 1,
    'KRW': 1, 'PYG': 1, 'RWF': 1, 'TWD': 1, 'UGX': 1, 'VND': 1,
    'VUV': 1, 'XAF': 1, 'XOF': 1, 'XPF': 1,
    'MGA': 5, 'MRO': 5,
}


def _get_offset(currency):
    """Get the currency offset divisor. Default 100 for most currencies."""
    return CURRENCY_OFFSETS.get(currency, 100)

# Common currency symbols — matches background.js getCurrencySymbol()
_CURRENCY_SYMBOLS = {
    'USD': '$', 'EUR': '€', 'GBP': '£', 'JPY': '¥', 'CNY': '¥', 'KRW': '₩',
    'INR': '₹', 'BRL': 'R$', 'CAD': 'CA$', 'AUD': 'A$', 'HKD': 'HK$',
    'TWD': 'NT$', 'SGD': 'S$', 'MXN': 'MX$', 'NZD': 'NZ$', 'THB': '฿',
    'VND': '₫', 'IDR': 'Rp', 'MYR': 'RM', 'PHP': '₱', 'TRY': '₺',
    'RUB': '₽', 'PLN': 'zł', 'CZK': 'Kč', 'SEK': 'kr', 'NOK': 'kr',
    'DKK': 'kr', 'CHF': 'CHF', 'ZAR': 'R', 'ARS': 'ARS$', 'CLP': 'CLP$',
    'COP': 'COL$', 'PEN': 'S/', 'ILS': '₪', 'EGP': 'E£', 'NGN': '₦',
    'SAR': 'SR', 'AED': 'AED', 'QAR': 'QR', 'KWD': 'KD', 'BHD': 'BD',
    'OMR': 'OMR', 'JOD': 'JD', 'PKR': 'Rs', 'BDT': '৳', 'LKR': 'Rs',
    'MMK': 'K', 'KHR': '៛', 'LAK': '₭', 'HUF': 'Ft', 'RON': 'lei',
    'BGN': 'лв', 'HRK': 'kn', 'ISK': 'kr', 'PYG': '₲', 'UYU': '$U',
    'CRC': '₡', 'GTQ': 'Q', 'BOB': 'Bs', 'DOP': 'RD$', 'HNL': 'L',
    'NIO': 'C$', 'UAH': '₴', 'GEL': '₾', 'KZT': '₸',
}


def _get_currency_symbol(currency_code):
    return _CURRENCY_SYMBOLS.get(currency_code, currency_code + ' ')


bp = Blueprint('api_receive', __name__, url_prefix='/api/receive')


def _extract_bm_info(acct):
    """Extract bm_id and bm_name from business/owner_business fields."""
    bm_id = ''
    bm_name = ''
    if isinstance(acct.get('business'), dict):
        bm_id = acct['business'].get('id', '')
    if not bm_id and isinstance(acct.get('owner_business'), dict):
        bm_id = acct['owner_business'].get('id', '')
    if isinstance(acct.get('owner_business'), dict):
        bm_name = acct['owner_business'].get('name', '')
    acct['bm_id'] = bm_id
    acct['bm_name'] = bm_name
    return bm_id, bm_name


def _get_user_id(data):
    """Resolve storage owner from authenticated extension session."""
    user = get_current_user()
    if user:
        return str(user.get('username', ''))
    return ''


@bp.route('/ad-account', methods=['POST'])
def receive_ad_account():
    """Receive single ad account data from getData action."""
    data = request.get_json(silent=True) or {}
    try:
        user_id = _get_user_id(data)
        if not user_id:
            return jsonify({'success': False, 'message': 'No user_id'}), 400
        account_data = data.get('data', data)
        if account_data.get('account_id'):
            # Extract BM info from owner_business (same logic as batch endpoint)
            _extract_bm_info(account_data)
            bm_id = account_data.get('bm_id', '')
            if bm_id:
                upsert_bm_ad_account(user_id, bm_id, account_data.get('account_id'), account_data.get('ownership', 'owned') or 'owned')
            upsert_ad_account(user_id, account_data)
            add_action_log('receive_ad_account', f"account_id={account_data['account_id']}", user_id)
            return jsonify({'success': True, 'message': 'Account saved'})
        return jsonify({'success': False, 'message': 'No account_id'}), 400
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@bp.route('/ad-accounts-batch', methods=['POST'])
def receive_ad_accounts_batch():
    """Receive batch ad accounts from getaduserList action."""
    data = request.get_json(silent=True) or {}
    try:
        user_id = _get_user_id(data)
        if not user_id:
            return jsonify({'success': False, 'message': 'No user_id'}), 400
        accounts = data.get('data', [])
        if not isinstance(accounts, list):
            accounts = [accounts]
        count = 0
        for acct in accounts:
            if not acct.get('account_id'):
                continue
            # Extract business info from business/owner_business fields
            bm_id, bm_name = _extract_bm_info(acct)
            if bm_id:
                upsert_bm_ad_account(user_id, bm_id, acct.get('account_id'), acct.get('ownership', 'owned') or 'owned')

            # Process account status
            status_map = {1: 'ACTIVE', 2: 'DISABLED', 3: 'UNSETTLED', 7: 'PENDING_RISK_REVIEW',
                          8: 'PENDING_SETTLEMENT', 9: 'IN_GRACE_PERIOD', 100: 'PENDING_CLOSURE',
                          101: 'CLOSED', 201: 'ANY_ACTIVE', 202: 'ANY_CLOSED'}
            raw_status = acct.get('account_status')
            if isinstance(raw_status, int):
                acct['account_status'] = status_map.get(raw_status, str(raw_status))

            # Process financial fields — match background.js logic exactly
            ratio = float(acct.get('account_currency_ratio_to_usd', 1) or 1)
            currency = acct.get('currency', 'USD')
            currency_symbol = _get_currency_symbol(currency)
            offset = _get_offset(currency)

            def _to_us(val_str):
                """USD = amount / ratio (ratio = units of local currency per 1 USD)."""
                try:
                    v = float(str(val_str).replace(',', ''))
                    if v == 0 or not ratio or ratio == 0:
                        return '$0'
                    result = v / ratio
                    if result != result:  # NaN check
                        return '$0'
                    return f"${result:,.2f}"
                except (ValueError, TypeError, ZeroDivisionError):
                    return '$0'

            def _fmt(v):
                return f"{v:,.2f}"

            # Balance: FB API returns cents for most currencies
            balance_raw = acct.get('balance', 0)
            try:
                balance_num = float(balance_raw)
            except (ValueError, TypeError):
                balance_num = 0
            balance_val = balance_num / offset
            acct['balance'] = _fmt(balance_val)
            acct['balance_tous'] = _to_us(acct['balance'])
            acct['balance'] = currency_symbol + acct['balance']

            # Threshold: also in cents
            thresh = 0
            if isinstance(acct.get('adspaymentcycle'), dict):
                pdata = acct['adspaymentcycle'].get('data', [])
                if pdata:
                    thresh = pdata[0].get('threshold_amount', 0)
            elif isinstance(acct.get('adspaymentcycle'), list) and acct['adspaymentcycle']:
                thresh = acct['adspaymentcycle'][0].get('threshold_amount', 0)
            try:
                thresh = float(thresh)
            except (ValueError, TypeError):
                thresh = 0
            thresh_val = thresh / offset
            acct['threshold_amount'] = _fmt(thresh_val) if thresh_val else '0'
            acct['threshold_amount_tous'] = _to_us(acct['threshold_amount']) if thresh_val else '$0'
            acct['threshold_amount'] = currency_symbol + acct['threshold_amount'] if thresh_val else '0'

            # DSL: divide by offset (same as balance/threshold)
            dsl = acct.get('adtrust_dsl', 0)
            try:
                dsl_num = float(dsl)
            except (ValueError, TypeError):
                dsl_num = 0
            if dsl_num == -1:
                acct['adtrust_dsl'] = '不限额'
                acct['adtrust_dsl_tous'] = '不限额'
            else:
                dsl_val = dsl_num / offset
                acct['adtrust_dsl'] = _fmt(dsl_val)
                acct['adtrust_dsl_tous'] = _to_us(acct['adtrust_dsl'])
                acct['adtrust_dsl'] = currency_symbol + acct['adtrust_dsl']

            # Spend: insights.spend is in base currency unit, no /100
            spend = 0
            if isinstance(acct.get('insights'), dict):
                idata = acct['insights'].get('data', [])
                if idata:
                    try:
                        spend = float(idata[0].get('spend', 0))
                    except (ValueError, TypeError):
                        spend = 0
            acct['amount_spent'] = _fmt(spend)
            acct['amount_spent_tous'] = _to_us(acct['amount_spent'])
            acct['amount_spent'] = currency_symbol + acct['amount_spent']

            # Payment card
            cards = []
            apm = acct.get('all_payment_methods', {})
            if isinstance(apm, dict):
                for cc in (apm.get('pm_credit_card', {}).get('data', [])):
                    if cc.get('display_string'):
                        cards.append(cc['display_string'])
            acct['paymentcard'] = ' | '.join(cards) if cards else acct.get('paymentcard', '')

            # Type & ownership
            acct['account_type'] = 'Business' if acct.get('business') else 'Personal Account'
            role_map = {'1001': 'Admin', '1002': 'Advertiser', '1003': 'Analyst',
                        1001: 'Admin', 1002: 'Advertiser', 1003: 'Analyst'}
            acct['ownership'] = role_map.get(acct.get('ownerrole', ''), 'Unknown')
            acct['ownershipid'] = str(acct.get('ownerrole', ''))

            # Owner business name
            if isinstance(acct.get('owner_business'), dict):
                acct['owner_business_name'] = acct['owner_business'].get('name', '')

            # Created time
            ct = acct.get('created_time')
            if ct and isinstance(ct, str) and 'T' in ct:
                acct['create_date'] = ct.split('T')[0]
            elif ct:
                acct['create_date'] = str(ct)

            # Funding source
            fsd = acct.get('funding_source_details')
            if isinstance(fsd, dict):
                acct['funding_source_details'] = fsd.get('display_string', '')
            elif fsd is None:
                acct['funding_source_details'] = ''

            upsert_ad_account(user_id, acct)
            count += 1
        add_action_log('receive_ad_accounts_batch', f"count={count}", user_id)
        return jsonify({'success': True, 'count': count})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@bp.route('/hidden-accounts', methods=['POST'])
def receive_hidden_accounts():
    """Receive hidden admin data from getHidde action."""
    data = request.get_json(silent=True) or {}
    try:
        user_id = _get_user_id(data)
        if not user_id:
            return jsonify({'success': False, 'message': 'No user_id'}), 400
        hidde_list = data.get('hidde', [])
        adlist = data.get('adlist', [])
        count = 0
        for item in hidde_list:
            if not item.get('success') or not item.get('accountId'):
                continue
            account_id = str(item['accountId'])
            users_str = item.get('data', '')
            if users_str:
                try:
                    users = json.loads(users_str) if isinstance(users_str, str) else users_str
                    if isinstance(users, list):
                        for u in users:
                            uid = u.get('uid') or u.get('id', '')
                            upsert_ad_account_user(
                                user_id, account_id, str(uid),
                                u.get('name', ''), str(u.get('role', '')),
                                1, json.dumps(u, default=str))
                            count += 1
                except (json.JSONDecodeError, TypeError):
                    pass
        add_action_log('receive_hidden_accounts', f"users_count={count}", user_id)
        return jsonify({'success': True, 'count': count})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@bp.route('/bm-list', methods=['POST'])
def receive_bm_list():
    """Receive BM list from getBmuserList action."""
    data = request.get_json(silent=True) or {}
    try:
        user_id = _get_user_id(data)
        if not user_id:
            return jsonify({'success': False, 'message': 'No user_id'}), 400
        bms = data.get('data', [])
        if isinstance(bms, dict) and isinstance(bms.get('data'), list):
            bms = bms.get('data', [])
        if not isinstance(bms, list):
            bms = [bms]
        count = 0
        for bm in bms:
            if not bm.get('id'):
                continue
            upsert_bm(user_id, bm)
            # If BM has ad accounts info
            for acct in bm.get('owned_ad_accounts', {}).get('data', []):
                account_id = acct.get('account_id') or acct.get('id')
                if account_id:
                    upsert_bm_ad_account(user_id, bm['id'], account_id, 'owned')
            for acct in bm.get('client_ad_accounts', {}).get('data', []):
                account_id = acct.get('account_id') or acct.get('id')
                if account_id:
                    upsert_bm_ad_account(user_id, bm['id'], account_id, 'client')
            count += 1
        add_action_log('receive_bm_list', f"count={count}", user_id)
        return jsonify({'success': True, 'count': count})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@bp.route('/pixels-batch', methods=['POST'])
def receive_pixels_batch():
    """Receive pixel list from refresh_pixels command."""
    data = request.get_json(silent=True) or {}
    try:
        user_id = _get_user_id(data)
        if not user_id:
            return jsonify({'success': False, 'message': 'No user_id'}), 400
        pixels = data.get('data', [])
        if isinstance(pixels, dict) and isinstance(pixels.get('data'), list):
            pixels = pixels.get('data', [])
        elif isinstance(pixels, dict) and isinstance(pixels.get('owned_pixels', {}).get('data'), list):
            owner_bm_id = pixels.get('id', '')
            owner_bm_name = pixels.get('name', '')
            pixels = [{
                'pixel_id': item.get('id', ''),
                'name': item.get('name', ''),
                'status': item.get('status', ''),
                'owner_bm_id': owner_bm_id,
                'owner_bm_name': owner_bm_name
            } for item in pixels.get('owned_pixels', {}).get('data', [])]
        if not isinstance(pixels, list):
            pixels = [pixels]
        count = 0
        for pixel in pixels:
            pixel_id = pixel.get('pixel_id') or pixel.get('id')
            if not pixel_id:
                continue
            upsert_pixel(user_id, {
                'pixel_id': pixel_id,
                'name': pixel.get('name', ''),
                'owner_bm_id': pixel.get('owner_bm_id', ''),
                'status': pixel.get('status', ''),
                'raw_data': pixel
            })
            count += 1
        add_action_log('receive_pixels_batch', f"count={count}", user_id)
        return jsonify({'success': True, 'count': count})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@bp.route('/pixel-users', methods=['POST'])
def receive_pixel_users():
    """Receive pixel user assignments from getPixelUser action."""
    data = request.get_json(silent=True) or {}
    try:
        user_id = _get_user_id(data)
        if not user_id:
            return jsonify({'success': False, 'message': 'No user_id'}), 400
        pixel_id = data.get('pixel_id', '')
        pixel_data = data.get('data', [])
        if pixel_id:
            users = pixel_data[0] if len(pixel_data) > 0 else []
            partners = pixel_data[1] if len(pixel_data) > 1 else []
            adaccounts = pixel_data[2] if len(pixel_data) > 2 else []
            upsert_pixel(user_id, {
                'pixel_id': pixel_id,
                'name': data.get('pixel_name', ''),
                'owner_bm_id': data.get('bm_id', ''),
                'assigned_users': users,
                'assigned_partners': partners,
                'assigned_adaccounts': adaccounts
            })
            # Save associations
            for u in (users.get('data', []) if isinstance(users, dict) else users if isinstance(users, list) else []):
                aid = u.get('account_id') or u.get('id', '')
                upsert_pixel_association(user_id, pixel_id, 'user', str(aid), u.get('name', ''), json.dumps(u, default=str))
            for p in (partners.get('data', []) if isinstance(partners, dict) else partners if isinstance(partners, list) else []):
                aid = p.get('account_id') or p.get('id', '')
                upsert_pixel_association(user_id, pixel_id, 'partner', str(aid), p.get('name', ''), json.dumps(p, default=str))
            for a in (adaccounts.get('data', []) if isinstance(adaccounts, dict) else adaccounts if isinstance(adaccounts, list) else []):
                aid = a.get('account_id') or a.get('id', '')
                upsert_pixel_association(user_id, pixel_id, 'adaccount', str(aid), a.get('name', ''), json.dumps(a, default=str))
            add_action_log('receive_pixel_users', f"pixel_id={pixel_id}", user_id)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@bp.route('/pixel-purchases', methods=['POST'])
def receive_pixel_purchases():
    """Receive pixel purchase events from getPurchaseList action."""
    data = request.get_json(silent=True) or {}
    try:
        user_id = _get_user_id(data)
        if not user_id:
            return jsonify({'success': False, 'message': 'No user_id'}), 400
        purchases = data.get('data', {})
        count = 0
        for pixel_id, events in purchases.items():
            save_pixel_purchases(user_id, pixel_id, events)
            count += 1
        add_action_log('receive_pixel_purchases', f"pixels_count={count}", user_id)
        return jsonify({'success': True, 'count': count})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@bp.route('/ad-library-item', methods=['POST'])
def receive_ad_library_item():
    """Receive ad library item from content-video.js."""
    data = request.get_json(silent=True) or {}
    try:
        user_id = _get_user_id(data)
        if not user_id:
            return jsonify({'success': False, 'message': 'No user_id'}), 400
        items = data.get('items', [data] if data.get('ad_archive_id') else [])
        count = 0
        for item in items:
            if item.get('ad_archive_id'):
                upsert_ad_library_item(user_id, item)
                count += 1
        add_action_log('receive_ad_library_item', f"count={count}", user_id)
        return jsonify({'success': True, 'count': count})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@bp.route('/token-info', methods=['POST'])
def receive_token_info():
    """Receive token info from getEAAI action."""
    data = request.get_json(silent=True) or {}
    try:
        user_id = _get_user_id(data)
        if not user_id:
            return jsonify({'success': False, 'message': 'No user_id'}), 400
        set_extension_state(user_id, 'token_info', data)
        set_extension_state(user_id, 'last_token_time', data.get('timestamp', ''))
        add_action_log('receive_token_info', 'Token info updated', user_id)
        return jsonify({'success': True, 'user_id': user_id})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@bp.route('/account-dsl', methods=['POST'])
def receive_account_dsl():
    """Receive formatted_dsl push or DSL failure status from extension."""
    data = request.get_json(silent=True) or {}
    try:
        user_id = _get_user_id(data)
        if not user_id:
            return jsonify({'success': False, 'error': 'missing user_id'}), 400
        account_id = str(data.get('account_id', '')).strip()
        formatted_dsl = str(data.get('formatted_dsl', '')).strip()
        formatted_dsl_tous = str(data.get('formatted_dsl_tous', '')).strip()
        status = str(data.get('dsl_fetch_status', '')).strip() or ('success' if formatted_dsl else 'missing')
        error = str(data.get('dsl_fetch_error', '')).strip()
        source = str(data.get('dsl_fetch_source', '')).strip()
        attempts = data.get('dsl_fetch_attempts', 0)
        try:
            attempts = int(attempts or 0)
        except (TypeError, ValueError):
            attempts = 0
        if not account_id:
            return jsonify({'success': False, 'error': 'missing account_id'}), 400
        payload = {
            "formatted_dsl": formatted_dsl,
            "formatted_dsl_tous": formatted_dsl_tous,
            "dsl_fetch_status": status,
            "dsl_fetch_error": error,
            "dsl_fetch_attempts": attempts,
            "dsl_fetch_source": source,
        }
        update_account_dsl_status(user_id, account_id, payload)
        if formatted_dsl:
            add_action_log('receive_account_dsl', f'account={account_id}, dsl={formatted_dsl}', user_id)
        else:
            add_action_log('receive_account_dsl_status', f'account={account_id}, status={status}, attempts={attempts}, error={error}', user_id)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@bp.route('/heartbeat', methods=['POST'])
def receive_heartbeat():
    """Receive heartbeat from extension."""
    data = request.get_json(silent=True) or {}
    try:
        user_id = _get_user_id(data)
        if not user_id:
            return jsonify({'success': True})  # heartbeat can be silent
        set_extension_state(user_id, 'heartbeat', {
            'timestamp': data.get('timestamp', ''),
            'version': data.get('version', ''),
            'status': 'connected'
        })
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@bp.route('/campaigns', methods=['POST'])
def receive_campaigns():
    """Receive campaign list from extension for an ad account."""
    data = request.get_json(silent=True) or {}
    try:
        user_id = _get_user_id(data)
        if not user_id:
            return jsonify({'success': False, 'error': 'missing user_id'}), 400
        account_id = str(data.get('account_id', ''))
        campaigns = data.get('campaigns', [])
        if not account_id:
            return jsonify({'success': False, 'error': 'missing account_id'}), 400
        count = 0
        for c in campaigns:
            upsert_campaign(user_id, account_id, c)
            count += 1
        add_action_log('receive_campaigns', f'account={account_id}, count={count}', user_id)
        return jsonify({'success': True, 'count': count})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

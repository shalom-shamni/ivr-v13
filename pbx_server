#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from flask import Flask, request, jsonify
import json
import logging
import os
from datetime import datetime
from typing import Dict, Any, Optional

# ==== Imports & Config ========================================================
try:
    from config import Config  # make sure your file name is config.py
except Exception:
    # very small fallback so the server can still run
    class Config:  # type: ignore
        LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
        LOG_FILE = os.getenv('LOG_FILE', 'pbx_system.log')
        DATABASE_PATH = os.getenv('DATABASE_PATH', 'pbx_system.db')
        ICOUNT_MOCK = True
        MOCK_RECEIPTS_PREFIX = 'DBG'

from database_handler import DatabaseHandler

# If you have a real ICount handler module, it will be used; otherwise we mock.
try:
    from icount_handler import ICountHandler  # pragma: no cover
except Exception:
    class ICountHandler:  # minimal stub if real provider is absent
        def create_receipt(self, receipt_data: Dict) -> Dict:
            return {
                'status': False,
                'message': 'Real ICount provider not configured',
            }


# ==== Logging ================================================================
logging.basicConfig(
    level=getattr(logging, str(getattr(Config, 'LOG_LEVEL', 'INFO')).upper()),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(getattr(Config, 'LOG_FILE', 'pbx_system.log'), encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


# ==== Mock provider for debug mode ===========================================
class MockReceiptProvider:
    def __init__(self, prefix: str = 'DBG'):
        self.prefix = prefix

    def create_receipt(self, receipt_data: Dict) -> Dict:
        now = datetime.now().strftime('%Y%m%d%H%M%S')
        return {
            'status': True,
            'doc_id': f"{self.prefix}_DOC_{now}",
            'doc_num': f"{self.prefix}-R{now[-8:]}",
            'message': 'Mock receipt created (debug mode)'
        }


# ==== Flask app ==============================================================
app = Flask(__name__)


# ==== PBX Handler ============================================================
class PBXHandler:
    def __init__(self):
        self.db = DatabaseHandler(getattr(Config, 'DATABASE_PATH', 'pbx_system.db'))
        # choose receipt provider by flag
        if bool(str(getattr(Config, 'ICOUNT_MOCK', 'true')).lower() == 'true'):
            self.icount = MockReceiptProvider(prefix=getattr(Config, 'MOCK_RECEIPTS_PREFIX', 'DBG'))
        else:
            self.icount = ICountHandler()
        self.current_calls: Dict[str, Dict[str, Any]] = {}

    # ---------- utilities ----------
    def get_customer_by_phone(self, phone_number: str) -> Optional[Dict]:
        return self.db.get_customer_by_phone(phone_number)

    def is_subscription_active(self, customer: Dict) -> bool:
        return self.db.is_subscription_active(customer)

    def show_error_and_return_to_main(self) -> Dict:
        return {
            "type": "simpleMenu",
            "name": "systemError",
            "times": 1,
            "timeout": 10,
            "enabledKeys": "0",
            "setMusic": "no",
            "files": [
                {"text": "אירעה שגיאה במערכת. לחץ 0 לחזרה לתפריט הראשי.", "activatedKeys": "0"}
            ]
        }

    # ---------- profile wizard ----------
    def require_profile_or_main(self, call_id: str, phone: str) -> Dict:
        customer = self.get_customer_by_phone(phone)
        if not customer:
            return handle_new_customer()
        if not self.db.is_profile_complete(customer):
            # missing tz_id
            if not customer.get('tz_id'):
                return {
                    "type": "getDTMF", "name": "newCustomerID",
                    "max": 10, "min": 8, "timeout": 30,
                    "confirmType": "digits", "setMusic": "no",
                    "files": [{"text": "אנא הקש תעודת זהות (8–10 ספרות).", "activatedKeys": "0,1,2,3,4,5,6,7,8,9"}]
                }
            # missing owner_age
            if customer.get('owner_age') is None:
                return {
                    "type": "getDTMF", "name": "ownerAge",
                    "max": 2, "min": 1, "timeout": 20, "confirmType": "number",
                    "files": [{"text": "אנא הקש גיל בעל העסק (שתי ספרות).", "activatedKeys": "0,1,2,3,4,5,6,7,8,9"}]
                }
            # missing gender
            if not customer.get('gender'):
                return {
                    "type": "simpleMenu", "name": "gender",
                    "times": 1, "timeout": 15, "enabledKeys": "1,2",
                    "files": [{"text": "בחר מין: לחץ 1 לזכר, 2 לנקבה.", "activatedKeys": "1,2"}]
                }
            # missing num_children (from details table)
            details = self.db.get_customer_details(customer['id'])
            if not details or details.get('num_children') is None:
                return handle_update_personal_details()
        # all good
        return show_main_menu()

    # ---------- input routing ----------
    def handle_user_input(self, call_id: str, input_name: str, input_value: str) -> Dict:
        # store input
        call_data = self.current_calls.setdefault(call_id, {})
        call_data[input_name] = input_value
        # persist into calls table json
        self.db.update_call_data(call_id, {input_name: input_value})

        # dispatch by input name
        if input_name == 'newCustomer':
            return self.process_new_customer_choice(call_id, input_value)
        elif input_name == 'newCustomerID':
            return self.process_new_customer_id(call_id, input_value)
        elif input_name == 'renewSubscription':
            return self.process_renewal_choice(call_id, input_value)
        elif input_name == 'mainMenu':
            return self.process_main_menu_choice(call_id, input_value)
        elif input_name == 'ownerAge':
            return self.process_owner_age(call_id, input_value)
        elif input_name == 'gender':
            return self.process_gender(call_id, input_value)
        elif input_name == 'numChildren':
            return self.process_children_count(call_id, input_value)
        elif input_name.startswith('child_birth_year_'):
            return self.process_child_birth_year(call_id, input_name, input_value)
        elif input_name in ('spouse1_workplaces', 'spouse2_workplaces'):
            return self.process_spouse_workplaces(call_id, input_name, input_value)
        elif input_name == 'customerMessage':
            return self.process_customer_message(call_id, input_value)
        elif input_name == 'annualReport':
            return self.process_annual_report_choice(call_id, input_value)
        # receipt flow
        elif input_name == 'receiptAmount':
            return self.process_receipt_amount(call_id, input_value)
        elif input_name == 'clientPhone':
            return self.process_client_phone(call_id, input_value)
        elif input_name == 'clientIdNumber':
            return self.process_client_id(call_id, input_value)
        elif input_name == 'saveContactChoice':
            return self.process_save_contact_choice(call_id, input_value)
        elif input_name == 'receiptDescription':
            return self.process_receipt_description(call_id, input_value)
        else:
            logger.warning(f"Unrecognized input: {input_name}={input_value}")
            return show_main_menu()

    # ---------- profile steps ----------
    def process_new_customer_choice(self, call_id: str, choice: str) -> Dict:
        if choice == '1':
            return {
                "type": "getDTMF",
                "name": "newCustomerID",
                "max": 10, "min": 8, "timeout": 30,
                "confirmType": "digits", "setMusic": "no",
                "files": [{"text": "אנא הכנס את מספר הזהות שלך.", "activatedKeys": "0,1,2,3,4,5,6,7,8,9"}]
            }
        return show_main_menu()

    def process_new_customer_id(self, call_id: str, tz: str) -> Dict:
        phone = self.current_calls.get(call_id, {}).get('PBXphone')
        if not phone:
            return show_main_menu()
        try:
            cust = self.get_customer_by_phone(phone)
            if not cust:
                # create new base customer by phone
                customer_id = self.db.create_customer(phone_number=phone)
                cust = self.db.get_customer_by_id(customer_id)
            # update tz_id
            if cust:
                self.db.update_customer_profile(cust['id'], tz_id=tz)
            return self.require_profile_or_main(call_id, phone)
        except Exception as e:
            logger.exception("Registration failed")
            return {
                "type": "simpleMenu", "name": "registrationFail",
                "times": 1, "timeout": 7, "enabledKeys": "0",
                "files": [{"text": "הרשמה נכשלה. לחץ 0 לחזרה לתפריט הראשי.", "activatedKeys": "0"}]
            }

    def process_owner_age(self, call_id: str, age: str) -> Dict:
        phone = self.current_calls.get(call_id, {}).get('PBXphone')
        try:
            age_i = int(age)
            if age_i < 14 or age_i > 99:
                raise ValueError
            cust = self.get_customer_by_phone(phone)
            if cust:
                self.db.update_customer_profile(cust['id'], owner_age=age_i)
        except Exception:
            logger.warning("Invalid owner_age input")
        return self.require_profile_or_main(call_id, phone)

    def process_gender(self, call_id: str, choice: str) -> Dict:
        phone = self.current_calls.get(call_id, {}).get('PBXphone')
        val = 'male' if choice == '1' else 'female' if choice == '2' else None
        cust = self.get_customer_by_phone(phone)
        if cust and val:
            self.db.update_customer_profile(cust['id'], gender=val)
        return self.require_profile_or_main(call_id, phone)

    # ---------- receipt flow ----------
    def process_main_menu_choice(self, call_id: str, choice: str) -> Dict:
        if choice == '1':
            return handle_create_receipt()
        elif choice == '2':
            return handle_cancel_receipt()
        elif choice == '3':
            return handle_update_personal_details()
        elif choice == '4':
            return handle_show_benefits()
        elif choice == '5':
            return handle_leave_message()
        elif choice == '6':
            return handle_annual_report()
        elif choice == '0':
            return show_main_menu()
        return show_main_menu()

    def process_receipt_amount(self, call_id: str, amount: str) -> Dict:
        if amount == 'SKIP':
            return show_main_menu()
        try:
            amt = int(amount)
            if amt <= 0:
                raise ValueError
            return {
                "type": "getDTMF", "name": "clientPhone",
                "max": 11, "min": 9, "timeout": 30, "confirmType": "digits",
                "files": [{"text": "הקש מספר טלפון של הלקוח (9–11 ספרות).", "activatedKeys": "0,1,2,3,4,5,6,7,8,9"}]
            }
        except ValueError:
            return {
                "type": "simpleMenu", "name": "invalidAmount",
                "times": 1, "timeout": 10, "enabledKeys": "1,0",
                "files": [{"text": "סכום לא חוקי. לחץ 1 לנסות שוב או 0 לחזרה לתפריט הראשי.", "activatedKeys": "1,0"}]
            }

    def process_client_phone(self, call_id: str, phone: str) -> Dict:
        cd = self.current_calls.setdefault(call_id, {})
        cd['client_phone'] = phone
        return {
            "type": "getDTMF", "name": "clientIdNumber",
            "max": 10, "min": 0, "timeout": 20, "confirmType": "digits",
            "skipKey": "#", "skipValue": "", "setMusic": "no",
            "files": [{"text": "הקש תעודת זהות של הלקוח או לחץ # לדילוג.", "activatedKeys": "0,1,2,3,4,5,6,7,8,9,#"}]
        }

    def process_client_id(self, call_id: str, tz: str) -> Dict:
        cd = self.current_calls.setdefault(call_id, {})
        cd['client_tz'] = tz or None
        return {
            "type": "simpleMenu", "name": "saveContactChoice",
            "times": 1, "timeout": 15, "enabledKeys": "1,2",
            "files": [{"text": "לשמור את הלקוח באנשי קשר? לחץ 1 לשמירה, 2 להמשך בלי שמירה.", "activatedKeys": "1,2"}]
        }

    def process_save_contact_choice(self, call_id: str, choice: str) -> Dict:
        cd = self.current_calls.get(call_id, {})
        issuer_phone = cd.get('PBXphone')
        issuer = self.get_customer_by_phone(issuer_phone)
        if issuer and choice == '1':
            self.db.upsert_contact(
                customer_id=issuer['id'],
                phone=cd.get('client_phone'),
                tz_id=cd.get('client_tz'),
                name=None, business_name=None, email=None, notes="added_via_ivr"
            )
        return {
            "type": "getDTMF", "name": "receiptDescription",
            "max": 20, "min": 1, "timeout": 30, "confirmType": "digits",
            "skipKey": "#", "skipValue": "NO_DESCRIPTION",
            "files": [{"text": "הקש קוד תיאור קבלה או לחץ # לדילוג.", "activatedKeys": "0,1,2,3,4,5,6,7,8,9,#"}]
        }

    def process_receipt_description(self, call_id: str, description: str) -> Dict:
        cd = self.current_calls.get(call_id, {})
        amount = cd.get('receiptAmount')
        issuer_phone = cd.get('PBXphone')
        issuer = self.get_customer_by_phone(issuer_phone)
        if not (amount and issuer):
            logger.error("Missing data for receipt creation")
            return self.show_error_and_return_to_main()

        client_phone = cd.get('client_phone')
        client_contact_id = None
        if client_phone:
            contact = self.db.get_contact_by_phone(issuer['id'], client_phone)
            if contact:
                client_contact_id = contact['id']

        receipt_data = {
            'amount': int(amount),
            'description': description if description != 'NO_DESCRIPTION' else 'קבלה',
            'client_phone': client_phone,
            'client_tz': cd.get('client_tz')
        }

        receipt_id = self.db.create_receipt(issuer['id'], call_id, receipt_data)
        if client_contact_id:
            self.db.update_receipt(receipt_id, client_contact_id=client_contact_id)

        icount_result = self.icount.create_receipt(receipt_data)
        if icount_result.get('status'):
            self.db.update_receipt(
                receipt_id,
                icount_doc_id=icount_result.get('doc_id'),
                icount_doc_num=icount_result.get('doc_num'),
                icount_response=json.dumps(icount_result, ensure_ascii=False),
                status='completed'
            )
            return {
                "type": "simpleMenu", "name": "receiptSuccess",
                "times": 1, "timeout": 15, "enabledKeys": "0",
                "files": [{"text": f"הקבלה נוצרה בהצלחה. מספר: {icount_result.get('doc_num', 'לא זמין')}. לחץ 0 לחזרה לתפריט הראשי.",
                           "activatedKeys": "0"}]
            }
        else:
            self.db.update_receipt(
                receipt_id,
                icount_response=json.dumps(icount_result, ensure_ascii=False),
                status='failed'
            )
            return {
                "type": "simpleMenu", "name": "receiptFailed",
                "times": 1, "timeout": 15, "enabledKeys": "1,0",
                "files": [{"text": "שגיאה ביצירת הקבלה. לחץ 1 לנסות שוב או 0 לתפריט הראשי.", "activatedKeys": "1,0"}]
            }

    # ---------- personal details / benefits ----------
    def process_children_count(self, call_id: str, num_children: str) -> Dict:
        try:
            n = int(num_children)
            if n < 0 or n > 20:
                raise ValueError
            cd = self.current_calls.setdefault(call_id, {})
            cd['children_count'] = n
            cd['current_child'] = 1
            if n == 0:
                return self.ask_spouse_workplaces(call_id, 1)
            return {
                "type": "getDTMF", "name": "child_birth_year_1",
                "max": 4, "min": 4, "timeout": 20, "confirmType": "number",
                "files": [{"text": "אנא הכנס את שנת הלידה של הילד הראשון (4 ספרות).", "activatedKeys": "0,1,2,3,4,5,6,7,8,9"}]
            }
        except ValueError:
            return self.show_error_and_return_to_main()

    def process_child_birth_year(self, call_id: str, input_name: str, birth_year: str) -> Dict:
        try:
            year = int(birth_year)
            current_year = datetime.now().year
            if year < current_year - 50 or year > current_year:
                raise ValueError
            cd = self.current_calls.setdefault(call_id, {})
            lst = cd.setdefault('children_birth_years', [])
            lst.append(year)
            current_child = cd.get('current_child', 1)
            total_children = cd.get('children_count', 0)
            if current_child < total_children:
                cd['current_child'] = current_child + 1
                return {
                    "type": "getDTMF", "name": f"child_birth_year_{current_child + 1}",
                    "max": 4, "min": 4, "timeout": 20, "confirmType": "number",
                    "files": [{"text": f"אנא הכנס את שנת הלידה של ילד מספר {current_child + 1} (4 ספרות).", "activatedKeys": "0,1,2,3,4,5,6,7,8,9"}]
                }
            else:
                return self.ask_spouse_workplaces(call_id, 1)
        except ValueError:
            return self.show_error_and_return_to_main()

    def ask_spouse_workplaces(self, call_id: str, spouse_num: int) -> Dict:
        spouse_text = "הראשון" if spouse_num == 1 else "השני"
        return {
            "type": "getDTMF", "name": f"spouse{spouse_num}_workplaces",
            "max": 2, "min": 1, "timeout": 20, "confirmType": "number",
            "files": [{"text": f"אנא הכנס את מספר מקומות העבודה של בן/בת הזוג {spouse_text}.", "activatedKeys": "0,1,2,3,4,5,6,7,8,9"}]
        }

    def process_spouse_workplaces(self, call_id: str, input_name: str, workplaces: str) -> Dict:
        try:
            count = int(workplaces)
            if count < 0 or count > 10:
                raise ValueError
            cd = self.current_calls.setdefault(call_id, {})
            cd[input_name] = count
            if input_name == 'spouse1_workplaces':
                return self.ask_spouse_workplaces(call_id, 2)
            else:
                # persist details
                phone = cd.get('PBXphone')
                cust = self.get_customer_by_phone(phone)
                if cust:
                    self.db.update_customer_details(
                        cust['id'],
                        num_children=cd.get('children_count', 0),
                        children_birth_years=json.dumps(cd.get('children_birth_years', []), ensure_ascii=False),
                        spouse1_workplaces=cd.get('spouse1_workplaces', 0),
                        spouse2_workplaces=cd.get('spouse2_workplaces', 0)
                    )
                return {
                    "type": "simpleMenu", "name": "detailsUpdated",
                    "times": 1, "timeout": 10, "enabledKeys": "0",
                    "files": [{"text": "הפרטים עודכנו בהצלחה. לחץ 0 לחזרה לתפריט הראשי.", "activatedKeys": "0"}]
                }
        except ValueError:
            return self.show_error_and_return_to_main()

    def process_customer_message(self, call_id: str, message_result: str) -> Dict:
        cd = self.current_calls.get(call_id, {})
        phone = cd.get('PBXphone')
        cust = self.get_customer_by_phone(phone)
        if cust and message_result:
            self.db.save_message(cust['id'], call_id, message_file=message_result, duration=None)
        return {
            "type": "simpleMenu", "name": "messageReceived",
            "times": 1, "timeout": 10, "enabledKeys": "0",
            "files": [{"text": "ההודעה התקבלה. נחזור אליך תוך 48 שעות. לחץ 0 לחזרה לתפריט הראשי.", "activatedKeys": "0"}]
        }

    def process_annual_report_choice(self, call_id: str, choice: str) -> Dict:
        if choice == '1':
            cd = self.current_calls.get(call_id, {})
            phone = cd.get('PBXphone')
            cust = self.get_customer_by_phone(phone)
            if cust:
                self.db.request_annual_report(cust['id'])
            return {
                "type": "simpleMenu", "name": "reportRequested",
                "times": 1, "timeout": 10, "enabledKeys": "0",
                "files": [{"text": "בקשת הדיווח התקבלה. הדיווח יישלח אליך בהודעת SMS תוך 24 שעות. לחץ 0 לחזרה לתפריט הראשי.", "activatedKeys": "0"}]
            }
        return show_main_menu()


pbx_handler = PBXHandler()


# ==== Routes =================================================================
@app.route('/pbx', methods=['GET'])
def handle_pbx_request():
    try:
        # collect params
        call_params = {
            'PBXphone': request.args.get('PBXphone'),
            'PBXnum': request.args.get('PBXnum'),
            'PBXdid': request.args.get('PBXdid'),
            'PBXcallId': request.args.get('PBXcallId'),
            'PBXcallType': request.args.get('PBXcallType'),
            'PBXcallStatus': request.args.get('PBXcallStatus'),
            'PBXextensionId': request.args.get('PBXextensionId'),
            'PBXextensionPath': request.args.get('PBXextensionPath')
        }
        # copy extra params as well
        for k, v in request.args.items():
            if not k.startswith('PBX'):
                call_params[k] = v

        logger.info(f"Incoming PBX: {call_params}")
        pbx_handler.db.log_call(call_params)

        phone = call_params.get('PBXphone')
        call_id = call_params.get('PBXcallId') or ''
        # keep core PBX params in memory for this call
        core_keys = ['PBXphone','PBXnum','PBXdid','PBXcallType','PBXcallStatus','PBXextensionId','PBXextensionPath']
        pbx_handler.current_calls.setdefault(call_id, {}).update({k: call_params.get(k) for k in core_keys if call_params.get(k)})

        if not phone:
            return jsonify({"error": "חסר מספר טלפון"}), 400

        customer = pbx_handler.get_customer_by_phone(phone)
        if not customer:
            return jsonify(handle_new_customer())

        # subscription check (optional – keep behavior from previous version)
        if not pbx_handler.is_subscription_active(customer):
            return jsonify(handle_subscription_renewal())

        return jsonify(pbx_handler.require_profile_or_main(call_id, phone))
    except Exception:
        logger.exception("Error handling /pbx")
        return jsonify({"error": "שגיאה בטיפול בבקשה"}), 500


@app.route('/pbx/menu/<menu_name>', methods=['GET'])
def handle_menu_choice(menu_name: str):
    try:
        call_id = request.args.get('PBXcallId') or ''
        # keep core params for flow continuity
        core_keys = ['PBXphone','PBXnum','PBXdid','PBXcallType','PBXcallStatus','PBXextensionId','PBXextensionPath']
        core = {k: request.args.get(k) for k in core_keys if request.args.get(k)}
        if call_id:
            pbx_handler.current_calls.setdefault(call_id, {}).update(core)

        # value may come in parameter named like menu_name, or any of known keys
        value = request.args.get(menu_name)
        if value is None:
            for k in [
                'newCustomer','renewSubscription','mainMenu','newCustomerID','ownerAge','gender',
                'receiptAmount','clientPhone','clientIdNumber','saveContactChoice','receiptDescription',
                'cancelReceiptId','numChildren','spouse1_workplaces','spouse2_workplaces',
                'annualReport','customerMessage'
            ]:
                if k in request.args:
                    menu_name, value = k, request.args.get(k)
                    break

        if not value:
            return jsonify({
                "type": "simpleMenu", "name": "invalidChoice",
                "times": 1, "timeout": 5, "enabledKeys": "0",
                "files": [{"text": "לא התקבלה בחירה. לחץ 0 לחזרה לתפריט הראשי.", "activatedKeys": "0"}]
            })

        resp = pbx_handler.handle_user_input(call_id, menu_name, value)
        return jsonify(resp)
    except Exception:
        logger.exception("Error handling /pbx/menu")
        return jsonify({"error": "שגיאה בטיפול בבחירה"}), 500


# ==== Menu helpers ============================================================
def handle_new_customer() -> Dict:
    return {
        "type": "simpleMenu", "name": "newCustomer",
        "times": 1, "timeout": 10, "enabledKeys": "1,2", "setMusic": "no",
        "files": [{
            "text": "שלום וברוך הבא. נראה שאין לך עדיין מנוי במערכת שלנו. לחץ 1 להצטרפות למערכת, או לחץ 2 לחזרה לתפריט הקודם.",
            "activatedKeys": "1,2"
        }]
    }


def handle_subscription_renewal() -> Dict:
    return {
        "type": "simpleMenu", "name": "renewSubscription",
        "times": 1, "timeout": 10, "enabledKeys": "1,2", "setMusic": "no",
        "files": [{
            "text": "המנוי שלך פג תוקף. לחץ 1 לחידוש המנוי, או לחץ 2 לחזרה לתפריט הקודם.",
            "activatedKeys": "1,2"
        }]
    }


def show_main_menu() -> Dict:
    return {
        "type": "simpleMenu", "name": "mainMenu",
        "times": 3, "timeout": 15, "enabledKeys": "1,2,3,4,5,6,0", "setMusic": "yes",
        "files": [{
            "text": "שלום וברוך הבא למערכת השירותים שלנו. לחץ 1 להנפקת קבלה, לחץ 2 לביטול קבלה, לחץ 3 לעדכון פרטים אישיים, לחץ 4 לשמיעת זכויות מגיעות, לחץ 5 להשארת הודעה, לחץ 6 לבקשת דיווח שנתי, לחץ 0 לחזרה.",
            "activatedKeys": "1,2,3,4,5,6,0"
        }]
    }


def handle_create_receipt() -> Dict:
    return {
        "type": "getDTMF", "name": "receiptAmount",
        "max": 7, "min": 1, "timeout": 30, "confirmType": "number",
        "files": [{"text": "הקש סכום קבלה בשקלים (ללא אגורות).", "activatedKeys": "0,1,2,3,4,5,6,7,8,9"}]
    }


def handle_cancel_receipt() -> Dict:
    return {
        "type": "getDTMF", "name": "cancelReceiptId",
        "max": 10, "min": 1, "timeout": 30, "confirmType": "digits",
        "files": [{"text": "אנא הכנס את מספר הקבלה לביטול.", "activatedKeys": "0,1,2,3,4,5,6,7,8,9"}]
    }


def handle_update_personal_details() -> Dict:
    return {
        "type": "getDTMF", "name": "numChildren",
        "max": 2, "min": 1, "timeout": 20, "confirmType": "number",
        "files": [{"text": "אנא הכנס את מספר הילדים.", "activatedKeys": "0,1,2,3,4,5,6,7,8,9"}]
    }


def handle_show_benefits() -> Dict:
    return {
        "type": "simpleMenu", "name": "benefitsMenu",
        "times": 1, "timeout": 30, "enabledKeys": "1,0",
        "files": [{"text": "על בסיס הנתונים שלך, אתה זכאי למענק עבודה בסך 2000 שקל ולדמי לידה בסך 1500 שקל. לחץ 1 לפרטים נוספים או 0 לחזרה לתפריט הראשי.", "activatedKeys": "1,0"}]
    }


def handle_leave_message() -> Dict:
    return {
        "type": "record", "name": "customerMessage",
        "max": 180, "min": 3, "confirm": "confirmOnly",
        "fileName": f"message_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
        "files": [{"text": "אנא השאר את ההודעה שלך לאחר הצפצוף. לחץ # לסיום ההקלטה.", "activatedKeys": "NONE"}]
    }


def handle_annual_report() -> Dict:
    return {
        "type": "simpleMenu", "name": "annualReport",
        "times": 1, "timeout": 15, "enabledKeys": "1,0",
        "files": [{"text": "הדיווח השנתי שלך יישלח אליך בהודעת SMS תוך 24 שעות. לחץ 1 לאישור או 0 לביטול.", "activatedKeys": "1,0"}]
    }


if __name__ == '__main__':
    # DO NOT seed demo data here in production.
    app.run(host=getattr(Config, 'HOST', '0.0.0.0'), port=int(getattr(Config, 'PORT', 5000)), debug=bool(str(getattr(Config, 'DEBUG', 'true')).lower() == 'true'))

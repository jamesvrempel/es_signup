# Copyright (c) 2026, Enterprise Systems Australia and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit
from frappe.utils import cint


def get_settings():
	return frappe.get_single("ES Signup Settings")


def guard_enabled(settings=None):
	settings = settings or get_settings()
	if not settings.enable_signup:
		frappe.throw(_("Sign-up is currently closed on this site."), title=_("Not Allowed"))
	return settings


def build_request(**kwargs):
	"""Create the request as Administrator — Guest holds no permissions on the DocType."""
	doc = frappe.new_doc("ES Signup Request")
	doc.first_name = (kwargs.get("first_name") or "").strip()
	doc.last_name = (kwargs.get("last_name") or "").strip()
	doc.email = (kwargs.get("email") or "").strip().lower()
	doc.mobile_no = (kwargs.get("mobile_no") or "").strip()
	doc.company_name = (kwargs.get("company_name") or "").strip()
	doc.job_title = (kwargs.get("job_title") or "").strip()
	doc.reason = (kwargs.get("reason") or "").strip()

	account_type = kwargs.get("account_type") or "Customer"
	if account_type not in ("Customer", "System User"):
		account_type = "Customer"
	doc.account_type = account_type

	doc.source_site = frappe.local.site
	doc.source_page = kwargs.get("source_page") or ""
	doc.ip_address = frappe.local.request_ip
	if frappe.request:
		doc.user_agent = (frappe.request.headers.get("User-Agent") or "")[:500]

	doc.insert(ignore_permissions=True)
	return doc


# ----------------------------------------------------------------------
# public form at /signup
# ----------------------------------------------------------------------
@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(key="email", limit=3, seconds=60 * 60, ip_based=True)
def submit_signup_request(
	first_name,
	email,
	last_name=None,
	account_type="Customer",
	mobile_no=None,
	company_name=None,
	job_title=None,
	reason=None,
	source_page=None,
	website=None,
):
	settings = guard_enabled()

	# Honeypot: real people leave this hidden field empty.
	if website:
		return {"ok": True, "message": _("Thanks — we'll be in touch.")}

	if account_type == "System User" and not settings.allow_system_user_requests:
		account_type = "Customer"

	build_request(
		first_name=first_name,
		last_name=last_name,
		email=email,
		account_type=account_type,
		mobile_no=mobile_no,
		company_name=company_name,
		job_title=job_title,
		reason=reason,
		source_page=source_page,
	)

	return {
		"ok": True,
		"message": settings.success_message
		or _("Thanks. Your request has been sent for approval — we'll email you once it's reviewed."),
	}


# ----------------------------------------------------------------------
# override of Frappe's built-in /login#signup
# ----------------------------------------------------------------------
@frappe.whitelist(allow_guest=True)
@rate_limit(key="email", limit=3, seconds=60 * 60, ip_based=True)
def sign_up(email, full_name, redirect_to=None):
	"""Drop-in replacement for frappe.core.doctype.user.user.sign_up.

	Returns the same (status, message) contract the login page expects:
	0 = rejected/known, 1 = check your email, 2 = awaiting administrator.
	"""
	settings = get_settings()

	if not settings.enable_signup or not settings.override_login_signup:
		from frappe.core.doctype.user.user import sign_up as core_sign_up

		return core_sign_up(email, full_name, redirect_to)

	email = (email or "").strip().lower()

	if frappe.db.exists("User", email):
		user = frappe.get_doc("User", email)
		return 0, _("Registered but disabled") if user.disabled else _("Already Registered")

	if frappe.db.exists("ES Signup Request", {"email": email, "status": "Pending Approval"}):
		return 2, _("Your request is already with our team for approval.")

	parts = (full_name or "").strip().split(" ", 1)
	build_request(
		first_name=parts[0] or email,
		last_name=parts[1] if len(parts) > 1 else None,
		email=email,
		account_type="Customer",
		source_page="/login#signup",
	)

	return 2, _("Thanks — your request has been sent for approval. We'll email you once it's reviewed.")


# ----------------------------------------------------------------------
# email link actions
# ----------------------------------------------------------------------
def load_for_token(name, token):
	if not frappe.db.exists("ES Signup Request", name):
		frappe.throw(_("This request no longer exists."), frappe.DoesNotExistError)

	doc = frappe.get_doc("ES Signup Request", name)
	doc.verify_action_token(token)
	return doc


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(key="name", limit=10, seconds=60 * 60, ip_based=True)
def process_email_action(name, token, action, reason=None):
	"""Called by the POST from /signup-action. A GET never changes anything,
	so link-scanners and mail previews cannot approve an account."""
	doc = load_for_token(name, token)

	settings = get_settings()
	approver = (settings.get_approver_emails() or ["Administrator"])[0]
	actioned_by = approver if frappe.db.exists("User", approver) else "Administrator"

	if action == "approve":
		doc.approve(channel="Email Link", actioned_by=actioned_by)
		return {
			"ok": True,
			"status": "Approved",
			"message": _("Approved. {0} has been created and emailed a link to set a password.").format(
				doc.email
			),
		}

	if action == "reject":
		doc.reject(reason=reason, channel="Email Link", actioned_by=actioned_by)
		return {"ok": True, "status": "Rejected", "message": _("Rejected. No account was created.")}

	frappe.throw(_("Unknown action."))


@frappe.whitelist()
def resend_approval_email(name):
	doc = frappe.get_doc("ES Signup Request", name)
	doc.check_permission("write")

	if doc.status != "Pending Approval":
		frappe.throw(_("Only pending requests can be re-sent."))

	doc.notify_approvers()
	return {"ok": True}


def get_pending_count():
	return cint(
		frappe.db.count("ES Signup Request", {"status": "Pending Approval"})
	)

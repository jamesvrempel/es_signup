# Copyright (c) 2026, Enterprise Systems Australia and contributors
# For license information, please see license.txt

import hashlib
import hmac

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import (
	add_to_date,
	get_url,
	now_datetime,
	validate_email_address,
)


def hash_token(token: str) -> str:
	return hashlib.sha256((token or "").encode("utf-8")).hexdigest()


class ESSignupRequest(Document):
	# ------------------------------------------------------------------
	# lifecycle
	# ------------------------------------------------------------------
	def validate(self):
		self.email = (self.email or "").strip().lower()
		validate_email_address(self.email, throw=True)

		if not self.status:
			self.status = "Pending Approval"

		self.validate_email_domain()
		self.validate_duplicates()

	def validate_email_domain(self):
		if self.status != "Pending Approval" or not self.is_new():
			return

		settings = frappe.get_single("ES Signup Settings")
		domain = self.email.rsplit("@", 1)[-1]

		blocked = [d.strip().lower() for d in (settings.blocked_domains or "").splitlines() if d.strip()]
		if domain in blocked:
			frappe.throw(_("Sign-ups from {0} addresses are not accepted.").format(domain))

		allowed = [d.strip().lower() for d in (settings.allowed_domains or "").splitlines() if d.strip()]
		if allowed and domain not in allowed:
			frappe.throw(
				_("Sign-ups are limited to approved email domains. Contact us if you need access.")
			)

	def validate_duplicates(self):
		if not self.is_new():
			return

		if frappe.db.exists("User", {"name": self.email}):
			frappe.throw(_("An account already exists for {0}. Try signing in or resetting your password.").format(self.email))

		pending = frappe.db.exists(
			"ES Signup Request",
			{"email": self.email, "status": "Pending Approval", "name": ("!=", self.name or "")},
		)
		if pending:
			frappe.throw(_("A request for {0} is already awaiting approval.").format(self.email))

	def after_insert(self):
		self.notify_approvers()

	def on_update(self):
		"""Runs for desk buttons, workflow transitions and email-link actions alike."""
		if not self.has_value_changed("status"):
			return

		if self.status == "Approved":
			self.provision_account()
		elif self.status == "Rejected":
			self.send_rejection_email()

	# ------------------------------------------------------------------
	# tokens
	# ------------------------------------------------------------------
	def issue_action_token(self) -> str:
		settings = frappe.get_single("ES Signup Settings")
		hours = int(settings.token_validity_hours or 168)
		token = frappe.generate_hash(length=48)

		self.db_set("action_token_hash", hash_token(token), update_modified=False)
		self.db_set(
			"token_expires_on", add_to_date(now_datetime(), hours=hours), update_modified=False
		)
		return token

	def verify_action_token(self, token: str):
		if not self.action_token_hash:
			frappe.throw(_("This approval link is no longer valid."), frappe.PermissionError)

		if not hmac.compare_digest(self.action_token_hash, hash_token(token)):
			frappe.throw(_("This approval link is not valid."), frappe.PermissionError)

		if self.token_expires_on and now_datetime() > self.token_expires_on:
			frappe.throw(
				_("This approval link expired on {0}. Open the request in ES ERP to action it.").format(
					frappe.format_value(self.token_expires_on, {"fieldtype": "Datetime"})
				),
				frappe.PermissionError,
			)

	def clear_action_token(self):
		self.db_set("action_token_hash", None, update_modified=False)
		self.db_set("token_expires_on", None, update_modified=False)

	# ------------------------------------------------------------------
	# actions
	# ------------------------------------------------------------------
	@frappe.whitelist()
	def approve(self, channel="Desk", actioned_by=None):
		if self.status != "Pending Approval":
			frappe.throw(_("This request has already been {0}.").format(self.status.lower()))

		self.status = "Approved"
		self.approved_by = actioned_by or frappe.session.user
		self.actioned_on = now_datetime()
		self.action_channel = channel
		self.save(ignore_permissions=True)
		self.clear_action_token()
		return self

	@frappe.whitelist()
	def reject(self, reason=None, channel="Desk", actioned_by=None):
		if self.status != "Pending Approval":
			frappe.throw(_("This request has already been {0}.").format(self.status.lower()))

		self.status = "Rejected"
		self.rejection_reason = reason
		self.approved_by = actioned_by or frappe.session.user
		self.actioned_on = now_datetime()
		self.action_channel = channel
		self.save(ignore_permissions=True)
		self.clear_action_token()
		return self

	# ------------------------------------------------------------------
	# provisioning
	# ------------------------------------------------------------------
	def provision_account(self):
		settings = frappe.get_single("ES Signup Settings")

		user = self.create_user(settings)
		if not user:
			return

		if self.account_type == "Customer" and settings.create_customer_record:
			self.create_customer_and_contact(settings)

		self.send_welcome_email(user, settings)

	def create_user(self, settings):
		if self.created_user:
			return frappe.get_doc("User", self.created_user)

		if frappe.db.exists("User", self.email):
			user = frappe.get_doc("User", self.email)
			self.db_set("created_user", user.name)
			return user

		user = frappe.new_doc("User")
		user.email = self.email
		user.first_name = self.first_name
		user.last_name = self.last_name
		user.mobile_no = self.mobile_no
		user.enabled = 1
		user.send_welcome_email = 0
		user.user_type = "System User" if self.account_type == "System User" else "Website User"
		user.flags.ignore_permissions = True
		user.flags.ignore_password_policy = True
		user.insert(ignore_permissions=True)

		roles = self.get_roles(settings)
		if roles:
			user.add_roles(*roles)

		self.db_set("created_user", user.name)
		frappe.msgprint(
			_("User {0} created.").format(frappe.bold(user.name)), alert=True, indicator="green"
		)
		return user

	def get_roles(self, settings):
		table = (
			settings.system_user_roles
			if self.account_type == "System User"
			else settings.website_user_roles
		)
		roles = [r.role for r in (table or []) if r.role]

		if not roles and self.account_type == "Customer":
			portal_default = frappe.get_single_value("Portal Settings", "default_role")
			if portal_default:
				roles = [portal_default]

		return [r for r in roles if frappe.db.exists("Role", r)]

	def create_customer_and_contact(self, settings):
		if not frappe.db.exists("DocType", "Customer"):
			return

		customer_name = (self.company_name or "").strip() or self.full_name()

		if not self.created_customer:
			existing = frappe.db.exists("Customer", {"customer_name": customer_name})
			if existing:
				self.db_set("created_customer", existing)
			else:
				customer = frappe.new_doc("Customer")
				customer.customer_name = customer_name
				customer.customer_type = "Company" if self.company_name else "Individual"
				if settings.default_customer_group and frappe.db.exists(
					"Customer Group", settings.default_customer_group
				):
					customer.customer_group = settings.default_customer_group
				if settings.default_territory and frappe.db.exists("Territory", settings.default_territory):
					customer.territory = settings.default_territory
				customer.insert(ignore_permissions=True)
				self.db_set("created_customer", customer.name)

		if not self.created_contact and frappe.db.exists("DocType", "Contact"):
			contact = frappe.new_doc("Contact")
			contact.first_name = self.first_name
			contact.last_name = self.last_name
			contact.user = self.created_user
			contact.append("email_ids", {"email_id": self.email, "is_primary": 1})
			if self.mobile_no:
				contact.append("phone_nos", {"phone": self.mobile_no, "is_primary_mobile_no": 1})
			contact.append(
				"links", {"link_doctype": "Customer", "link_name": self.created_customer}
			)
			contact.insert(ignore_permissions=True)
			self.db_set("created_contact", contact.name)

	# ------------------------------------------------------------------
	# email
	# ------------------------------------------------------------------
	def full_name(self):
		return " ".join([p for p in [self.first_name, self.last_name] if p])

	def notify_approvers(self):
		settings = frappe.get_single("ES Signup Settings")
		recipients = settings.get_approver_emails()
		if not recipients:
			frappe.log_error(
				"No approver email configured in ES Signup Settings", "ES Signup"
			)
			return

		token = self.issue_action_token()
		base = get_url()

		frappe.sendmail(
			recipients=recipients,
			subject=_("Access request: {0} ({1})").format(self.full_name(), self.email),
			template="signup_approval_request",
			args={
				"doc": self,
				"full_name": self.full_name(),
				"site": frappe.local.site,
				"site_url": base,
				"approve_url": f"{base}/signup-action?name={self.name}&token={token}&action=approve",
				"reject_url": f"{base}/signup-action?name={self.name}&token={token}&action=reject",
				"desk_url": f"{base}/app/es-signup-request/{self.name}",
				"expires_on": self.token_expires_on,
			},
			now=True,
		)

	def send_welcome_email(self, user, settings):
		if self.welcome_email_sent:
			return

		reset_link = user.reset_password(send_email=False)

		frappe.sendmail(
			recipients=[self.email],
			subject=settings.welcome_subject or _("Your ES ERP account is ready"),
			template="signup_approved",
			args={
				"full_name": self.full_name(),
				"reset_link": reset_link,
				"login_url": get_url("/login"),
				"account_type": self.account_type,
				"intro": settings.welcome_message,
				"site_url": get_url(),
			},
			now=True,
		)
		self.db_set("welcome_email_sent", 1)

	def send_rejection_email(self):
		settings = frappe.get_single("ES Signup Settings")
		if not settings.notify_applicant_on_rejection:
			return

		frappe.sendmail(
			recipients=[self.email],
			subject=_("About your access request"),
			template="signup_rejected",
			args={
				"full_name": self.full_name(),
				"reason": self.rejection_reason,
				"contact_email": settings.support_email or (settings.get_approver_emails() or [""])[0],
			},
			now=True,
		)

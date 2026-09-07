# Copyright (c) 2026, Enterprise Systems Australia and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import validate_email_address


class ESSignupSettings(Document):
	def validate(self):
		for email in self.get_approver_emails():
			validate_email_address(email, throw=True)

		if self.enable_signup and not self.get_approver_emails():
			frappe.throw(_("Add at least one approver email before enabling sign-up requests."))

		if self.token_validity_hours and self.token_validity_hours < 1:
			frappe.throw(_("Email link validity must be at least one hour."))

	def get_approver_emails(self):
		raw = (self.approver_emails or "").replace(",", "\n")
		return [line.strip() for line in raw.splitlines() if line.strip()]

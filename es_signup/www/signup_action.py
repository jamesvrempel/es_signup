# Copyright (c) 2026, Enterprise Systems Australia and contributors

import frappe
from frappe import _

no_cache = 1


def get_context(context):
	"""GET only ever renders a confirmation screen. The account is created by the
	POST this page makes, so mail scanners that follow links change nothing."""
	context.no_cache = 1
	context.name = frappe.form_dict.get("name")
	context.token = frappe.form_dict.get("token")
	context.action = frappe.form_dict.get("action")
	context.error = None
	context.doc = None

	if context.action not in ("approve", "reject"):
		context.error = _("That link is missing an action.")
		return context

	try:
		doc = frappe.get_doc("ES Signup Request", context.name)
		doc.verify_action_token(context.token)
	except frappe.DoesNotExistError:
		context.error = _("That request no longer exists.")
		return context
	except Exception as e:
		context.error = str(e)
		return context

	if doc.status != "Pending Approval":
		context.error = _("This request was already {0} on {1}.").format(
			doc.status.lower(),
			frappe.format_value(doc.actioned_on, {"fieldtype": "Datetime"}),
		)
		return context

	context.doc = doc
	context.full_name = doc.full_name()
	return context

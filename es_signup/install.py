# Copyright (c) 2026, Enterprise Systems Australia and contributors

import frappe

APPROVER_ROLE = "ES Signup Approver"
DEFAULT_APPROVER = "james.rempel@enterprisesystems.com.au"

WORKFLOW_NAME = "ES Signup Approval"
STATES = [
	("Pending Approval", "Warning"),
	("Approved", "Success"),
	("Rejected", "Danger"),
	("Cancelled", "Danger"),
]
ACTIONS = ["Approve", "Reject", "Cancel"]


def after_install():
	create_role()
	create_workflow()
	seed_settings()
	frappe.db.commit()


def create_role():
	if frappe.db.exists("Role", APPROVER_ROLE):
		return

	role = frappe.new_doc("Role")
	role.role_name = APPROVER_ROLE
	role.desk_access = 1
	role.insert(ignore_permissions=True)


def create_workflow():
	"""Optional but handy: gives the desk a proper approval trail.

	The workflow drives the same `status` field the buttons and email links use,
	so all three routes converge on ESSignupRequest.on_update().
	"""
	if frappe.db.exists("Workflow", WORKFLOW_NAME):
		return

	for state, style in STATES:
		if not frappe.db.exists("Workflow State", state):
			frappe.get_doc(
				{"doctype": "Workflow State", "workflow_state_name": state, "style": style}
			).insert(ignore_permissions=True)

	for action in ACTIONS:
		if not frappe.db.exists("Workflow Action Master", action):
			frappe.get_doc(
				{"doctype": "Workflow Action Master", "workflow_action_name": action}
			).insert(ignore_permissions=True)

	workflow = frappe.new_doc("Workflow")
	workflow.workflow_name = WORKFLOW_NAME
	workflow.document_type = "ES Signup Request"
	workflow.workflow_state_field = "status"
	workflow.is_active = 1
	workflow.send_email_alert = 0

	for state, _style in STATES:
		workflow.append(
			"states",
			{
				"state": state,
				"doc_status": "0",
				"allow_edit": "System Manager" if state == "Pending Approval" else APPROVER_ROLE,
			},
		)

	transitions = [
		("Pending Approval", "Approve", "Approved"),
		("Pending Approval", "Reject", "Rejected"),
		("Pending Approval", "Cancel", "Cancelled"),
	]
	for state, action, next_state in transitions:
		workflow.append(
			"transitions",
			{
				"state": state,
				"action": action,
				"next_state": next_state,
				"allowed": APPROVER_ROLE,
				"allow_self_approval": 1,
			},
		)

	workflow.insert(ignore_permissions=True)


def seed_settings():
	settings = frappe.get_single("ES Signup Settings")

	if not settings.approver_emails:
		settings.approver_emails = DEFAULT_APPROVER

	if not settings.token_validity_hours:
		settings.token_validity_hours = 168

	if not settings.website_user_roles and frappe.db.exists("Role", "Customer"):
		settings.append("website_user_roles", {"role": "Customer"})

	settings.enable_signup = 0  # switch on deliberately, per site
	settings.override_login_signup = 1
	settings.create_customer_record = 1
	settings.allow_system_user_requests = 1
	settings.notify_applicant_on_rejection = 1
	settings.flags.ignore_permissions = True
	settings.save(ignore_permissions=True)

	# Grant the approver role to the default approver if that user exists here.
	if frappe.db.exists("User", DEFAULT_APPROVER):
		user = frappe.get_doc("User", DEFAULT_APPROVER)
		if APPROVER_ROLE not in [r.role for r in user.roles]:
			user.add_roles(APPROVER_ROLE)

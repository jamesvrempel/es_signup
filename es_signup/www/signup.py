# Copyright (c) 2026, Enterprise Systems Australia and contributors

import frappe

no_cache = 1


def get_context(context):
	settings = frappe.get_single("ES Signup Settings")

	context.enabled = bool(settings.enable_signup)
	context.form_intro = settings.form_intro
	context.allow_system_user_requests = bool(settings.allow_system_user_requests)
	context.support_email = settings.support_email
	context.no_cache = 1
	return context

# Copyright (c) 2026, Enterprise Systems Australia and contributors

app_name = "es_signup"
app_title = "ES Signup"
app_publisher = "Enterprise Systems Australia"
app_description = "Approval-gated account sign-up for ES ERP sites"
app_email = "james.rempel@enterprisesystems.com.au"
app_license = "MIT"
required_apps = ["frappe"]

# ----------------------------------------------------------------------
# Replace the login page's built-in signup card.
# Frappe renders this into the `for-signup` section of /login; it hands
# visitors off to /signup and repoints the "Sign up" links so that
# /login#signup lands on the full form.
# ----------------------------------------------------------------------
signup_form_template = "es_signup/templates/signup_form.html"

# ----------------------------------------------------------------------
# Route Frappe's built-in /login#signup into the approval queue.
# Still registered as a backstop: the handoff above is client-side, so a
# direct API call to sign_up must land in the same queue.
# ----------------------------------------------------------------------
override_whitelisted_methods = {
	"frappe.core.doctype.user.user.sign_up": "es_signup.api.sign_up",
}

after_install = "es_signup.install.after_install"

# Email templates live in es_signup/templates/emails and are referenced by
# name from frappe.sendmail(template="signup_approval_request", ...)
jinja = {
	"methods": [],
}

website_route_rules = []

# Uncomment to expire stale pending requests nightly.
# scheduler_events = {
# 	"daily": ["es_signup.tasks.expire_stale_requests"],
# }

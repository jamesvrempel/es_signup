// Copyright (c) 2026, Enterprise Systems Australia and contributors

frappe.ui.form.on("ES Signup Settings", {
	refresh(frm) {
		frm.add_web_link("/signup", __("Open public sign-up form"));

		if (frm.doc.enable_signup) {
			frm.dashboard.add_comment(
				__("Sign-up requests are open. Requests are emailed to: {0}", [
					(frm.doc.approver_emails || "").split("\n").join(", "),
				]),
				"blue",
				true
			);
		} else {
			frm.dashboard.add_comment(
				__("Sign-up is currently switched off. The public form returns a closed notice."),
				"orange",
				true
			);
		}
	},
});

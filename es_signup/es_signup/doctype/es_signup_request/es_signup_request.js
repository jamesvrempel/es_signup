// Copyright (c) 2026, Enterprise Systems Australia and contributors

frappe.ui.form.on("ES Signup Request", {
	refresh(frm) {
		frm.set_intro("");

		if (frm.doc.status === "Pending Approval" && !frm.is_new()) {
			frm.add_custom_button(__("Approve"), () => approve(frm)).addClass("btn-primary");
			frm.add_custom_button(__("Reject"), () => reject(frm));
			frm.add_custom_button(__("Resend approval email"), () => {
				frappe.call({
					method: "es_signup.api.resend_approval_email",
					args: { name: frm.doc.name },
					freeze: true,
				}).then(() => frappe.show_alert({ message: __("Sent"), indicator: "green" }));
			}, __("Actions"));
		}

		if (frm.doc.status === "Approved" && frm.doc.created_user) {
			frm.set_intro(
				__("Approved. Account {0} was created.", [frm.doc.created_user]),
				"green"
			);
		}

		if (frm.doc.account_type === "System User" && frm.doc.status === "Pending Approval") {
			frm.dashboard.add_comment(
				__("This request is for a System User, which uses a licensed seat."),
				"orange",
				true
			);
		}
	},
});

function approve(frm) {
	frappe.confirm(
		__("Create a {0} account for {1}?", [frm.doc.account_type, frm.doc.email]),
		() => {
			frm.call({ doc: frm.doc, method: "approve", freeze: true, freeze_message: __("Creating account…") })
				.then(() => frm.reload_doc());
		}
	);
}

function reject(frm) {
	frappe.prompt(
		[{ fieldname: "reason", fieldtype: "Small Text", label: __("Reason"), reqd: 1 }],
		(values) => {
			frm.call({
				doc: frm.doc,
				method: "reject",
				args: { reason: values.reason },
				freeze: true,
			}).then(() => frm.reload_doc());
		},
		__("Reject request"),
		__("Reject")
	);
}

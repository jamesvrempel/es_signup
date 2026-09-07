frappe.listview_settings["ES Signup Request"] = {
	add_fields: ["status", "account_type"],
	get_indicator(doc) {
		const map = {
			"Pending Approval": "orange",
			Approved: "green",
			Rejected: "red",
			Cancelled: "gray",
		};
		return [__(doc.status), map[doc.status] || "gray", "status,=," + doc.status];
	},
};

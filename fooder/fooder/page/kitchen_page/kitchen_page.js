frappe.pages['kitchen-page'].on_page_load = function(wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: 'Kitchen Page',
		single_column: true
	});
}
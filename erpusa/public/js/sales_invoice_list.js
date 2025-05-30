frappe.listview_settings["Sales Invoice"] = {
    onload: function(listview) {
        listview.page.add_button('Get Selected', () => {
            let selected = listview.get_checked_items();
            console.log("Selected items:", selected);

            // Do something with the selected documents
            frappe.msgprint(__('Selected: ') + selected.map(d => d.name).join(', '));
        });
    }
};
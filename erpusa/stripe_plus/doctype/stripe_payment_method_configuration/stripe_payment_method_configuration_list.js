frappe.listview_settings['Stripe Payment Method Configuration'] = {
    onload: function(listview) {
        listview.page.add_inner_button(__('Import from Stripe Account'), function() {
            prompt = frappe.prompt({
                label: 'Stripe Acccount Settings',
                fieldname: 'stripe_settings',
                fieldtype: 'Link',
                options: 'Stripe Settings',
                default: ""
            })
            prompt.set_title("Select Stripe Account Settings")
            prompt.set_primary_action("Continue", function(values) {
                prompt.hide()
                frappe.call({
                    method: "erpusa.stripe_plus.doctype.stripe_payment_method_configuration.stripe_payment_method_configuration.fetch_payment_configuration",
                    args: {
                        stripe_settings: values.stripe_settings? values.stripe_settings : "",
                    },
                    freeze: true,
                    freeze_message: __("Fetching Payment Configuration"),
                    callback: function(r) {
                        if (r.message) {
                            configurations_dialog = new frappe.ui.Dialog({
                                title: "Select Payment Configurations",
                                size: "extra-large",
                                fields: [
                                    {
                                        fieldtype: "HTML",
                                        options: `The following are payment configurations from ${values.stripe_settings}. To import a configuration from the list, tick its checkbox and click "Import Configurations".`
                                    },
                                    {
                                        label: "",
                                        fieldtype: "Table",
                                        fieldname: "configurations",
                                        cannot_add_rows: 1,
                                        cannot_delete_rows: 1,
                                        in_place_edit: 0,
                                        fields: [
                                            {
                                                label: "Name",
                                                fieldtype: "Data",
                                                fieldname: "configuration_name",
                                                in_list_view: 1,
                                                read_only: 1
                                            },
                                            {
                                                label: "Is Default",
                                                fieldtype: "Check",
                                                fieldname: "is_default",
                                                in_list_view: 1,
                                                read_only: 1
                                            },
                                            {
                                                label: "Is Active",
                                                fieldtype: "Check",
                                                fieldname: "enabled",
                                                in_list_view: 1,
                                                read_only: 1
                                            },
                                            {
                                                label: "Payment Methods",
                                                fieldtype: "Long Text",
                                                fieldname: "payment_methods_joined",
                                                in_list_view: 1,
                                                read_only: 1
                                            },
                                            {
                                                label: "Stripe ID",
                                                fieldtype: "Data",
                                                fieldname: "stripe_configuration_id",
                                                in_list_view: 1,
                                                read_only: 1
                                            }
                                        ],
                                        data: r.message
                                    }
                                ],
                                primary_action_label: "Import Configurations",
                                primary_action: function (data) {
                                    frappe.call({
                                        method: "erpusa.stripe_plus.doctype.stripe_payment_method_configuration.stripe_payment_method_configuration.import_configurations",
                                        freeze: true,
                                        freeze_message: __("Importing Configurations"),
                                        args: {
                                            configurations: data.configurations,
                                            stripe_settings: values.stripe_settings
                                        },
                                        callback: function(r) {
                                            configurations_dialog.hide()
                                        }
                                    })
                                }
                            })
    
                            configurations_dialog.show()
                        }
                    }
                });
            })
        });
    }
};
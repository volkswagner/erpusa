frappe.ui.form.on("Salary Structure Assignment", {
    refresh: function (frm) {
        frm.add_custom_button("Test Salary Slip", function() {
            let prompt = frappe.prompt([
                {
                    fieldname: "message",
                    fieldtype: "HTML",
                    options: `
                        Enter the values to override:
                        </br>
                        </br>
                    `
                },
                {
                    label: "Salary Structure",
                    fieldname: "salary_structure_section",
                    fieldtype: "Section Break"
                },
                {
                    label: "Gross Year to Date",
                    fieldname: "gross_to_date",
                    fieldtype: "Currency",
                    options: "currency"
                },
                {
                    label: "Base",
                    fieldname: "base",
                    fieldtype: "Currency",
                    options: "currency"
                },
                {
                    label: "Variable",
                    fieldname: "variable",
                    fieldtype: "Currency",
                    options: "currency"
                },
                {
                    label: "Salary Slip",
                    fieldname: "salary_slip_section",
                    fieldtype: "Section Break"
                },
                {
                    label: "Start Date",
                    fieldname: "start_date",
                    fieldtype: "Date"
                },
                {
                    label: "End Date",
                    fieldname: "end_date",
                    fieldtype: "Date"
                }
            ]);

            prompt.set_title(__("Test Salary Slip"));
            prompt.set_primary_action(__("View Salary Slip"), function (values) {
                frappe.db.get_value(
                    "Salary Structure",
                    frm.doc.salary_structure,
                    "salary_slip_based_on_timesheet",
                    (r) => {
                        const print_format = r.salary_slip_based_on_timesheet
                            ? "Salary Slip based on Timesheet"
                            : "Salary Slip Standard";
                        frappe.call({
                            method: "erpusa.payroll_plus.utils.salary_structure_assignment.test_salary_slip",
                            args: {
                                source_name: frm.doc.salary_structure,
                                employee: frm.doc.employee,
                                posting_date: frm.doc.from_date,
                                as_print: 1,
                                print_format: print_format,
                                for_preview: 1,
                                base: values.base,
                                start_date: values.start_date,
                                end_date: values.end_date
                            },
                            callback: function (r) {
                                const new_window = window.open();
                                new_window.document.write(r.message);
                            },
                        });
                    },
                );
            });
        }, "Tools");
    }
})
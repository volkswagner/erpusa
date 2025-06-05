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
                            method: "erpusa.payroll_plus.utils.salary_structure_assignment.test_salary_slip_printable",
                            args: {
                                salary_structure_assignment: frm.doc.name,
                                salary_structure: frm.doc.salary_structure,
                                employee: frm.doc.employee,
                                gross_to_date: values.gross_to_date || 0,
                                base: values.base? values.base : frm.doc.base,
                                variable: values.variable? values.variable : frm.doc.variable,
                                start_date: values.start_date,
                                end_date: values.end_date
                            },
                            callback: function (r) {
                                if (r.message) {
                                    let dialog = new frappe.ui.Dialog({
                                        title: __("Test Pay Slip"),
                                        size: "medium",
                                        fields: [
                                            {
                                                fieldtype: "HTML",
                                                options: r.message
                                            }
                                        ]
                                    })

                                    dialog.show()
                                }
                            },
                        });
                    },
                );
            });
        }, "Tools");

        frm.add_custom_button("Simulate Salary Slip", () => {
            let d = new frappe.ui.Dialog({
                title: "Simulate Salary Slip",
                fields: [
                { label: "Start Date", fieldname: "start_date", fieldtype: "Date", reqd: true },
                { label: "End Date", fieldname: "end_date", fieldtype: "Date", reqd: true },
                { label: "Override Gross Year To Date", fieldname: "gross_ytd", fieldtype: "Float" }
                ],
                primary_action_label: "Simulate",
                primary_action(values) {
                frappe.call({
                    method: "erpusa.payroll_plus.utils.salary_structure_assignment.test_salary_slip",
                    args: {
                    docname: frm.doc.name,
                    start_date: values.start_date,
                    end_date: values.end_date,
                    override_gross_ytd: values.gross_ytd || null
                    },
                    callback(r) {
                    console.log(r.message)
                    if (!r.message) return frappe.msgprint("No result.");

                    let earnings = r.message.earnings.map(e => `<tr><td>${e.component}</td><td>${e.amount}</td></tr>`).join("");
                    let deductions = r.message.deductions.map(d => `<tr><td>${d.component}</td><td>${d.amount}</td></tr>`).join("");

                    frappe.msgprint(`
                        <b>Gross YTD used:</b> ${r.message.gross_ytd_used || "N/A"}<br><br>
                        <b>Earnings</b><br><table class="table table-bordered">${earnings}</table>
                        <b>Deductions</b><br><table class="table table-bordered">${deductions}</table>
                        <b>Net Pay:</b> ${r.message.net_pay}
                    `);
                    d.hide();
                    }
                });
                }
            });

            d.show();
        }, "Tools");
    }
})
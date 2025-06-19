frappe.ui.form.on("Salary Slip", {

})

function populate_prev_gross_ytd(frm) {
    frappe.call({
        method: "erpusa.payroll_plus.utils.salary_structure_assignment.get_prev_gross_ytd",
        args: {
            "employee": frm.doc.employee 
        },
        callback: function(r) {
            if (r.message) {
                
            }
        }
    });
}
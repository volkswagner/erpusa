import frappe
from frappe import _
from hrms.payroll.doctype.salary_structure.salary_structure import make_salary_slip
from frappe.utils import getdate
from datetime import datetime

PERIOD_LENGTHS = {
    "Weekly": 7,
    "Fortnightly": 14,
    "Monthly": 30,
    "Bimonthly": 60,
}

@frappe.whitelist()
def test_salary_slip_printable(
    salary_structure_assignment,
    salary_structure,
    employee,
    gross_to_date=None,
    base=None,
    variable=None,
    start_date=None,
    end_date=None
):
    
    if (start_date and not end_date) or (not start_date and end_date):
        frappe.throw(_("Both start and end dates should be filled in."))

    if float(gross_to_date) < 0.0 or float(base) < 0.0 or float(variable) < 0.0:
        frappe.throw(_("Negative values are not allowed."))

    base = float(base)
    variable = float(variable)
    gross_year_to_date = 0.00
    gross_pay_base = 0.00
    gross_pay = 0.00
    gross_pay_multiplier = 1
    payroll_frequency = frappe.db.get_value("Salary Structure", salary_structure, "payroll_frequency")

    if frappe.db.count("Salary Slip", filters={"employee": employee}):
        latest_pay_slip = frappe.get_last_doc("Salary Slip", filters={"employee": employee})
        gross_year_to_date = frappe.db.get_value("Salary Slip", latest_pay_slip, "gross_year_to_date")

    if start_date and end_date:
        start_date = datetime.strptime(start_date, "%Y-%m-%d").date()
        end_date = datetime.strptime(end_date, "%Y-%m-%d").date()

        num_days = (end_date - start_date).days + 1

        if not (num_days % PERIOD_LENGTHS[payroll_frequency] == 0):
            frappe.throw(_(f"The number of days in date range does not fit in the {payroll_frequency} payroll frequency."))
        else:
            gross_pay_multiplier = num_days / PERIOD_LENGTHS[payroll_frequency]

    earnings = frappe.get_all(
        "Salary Detail",
        filters={"parent": salary_structure, "parentfield": "earnings"}, 
        fields=["salary_component", "abbr", "formula", "amount", "amount_based_on_formula", "do_not_include_in_total", "statistical_component"],
        order_by="idx asc"
    )

    deductions = frappe.get_all(
        "Salary Detail", 
        filters={"parent": salary_structure, "parentfield": "deductions"}, 
        fields=["salary_component", "abbr", "formula", "amount", "amount_based_on_formula", "do_not_include_in_total", "statistical_component"],
        order_by="idx asc"
    )

    component_name_abbr_matrix = {}
    earnings_matrix = {}
    deductions_matrix = {}
    earnings_total = 0.0
    deductions_total = 0.0

    for earning in earnings:
        exec(f"{earning['abbr']} = 0.0")

    for earning in earnings:
        component_name_abbr_matrix[earning['abbr']] = earning['salary_component']
        value = 0.00
        if not earning['amount_based_on_formula']:
            value = float(earning['amount'])

        else:
            if earning['formula']:
                value = float(eval(earning['formula'].replace("\n", " ")))

        exec(f"{earning['abbr']} = {str(value)}")

        earnings_matrix[earning['abbr']] = value

        if not earning['do_not_include_in_total'] and not earning["statistical_component"]:
            gross_pay_base = gross_pay_base + value
            earnings_total = earnings_total + value

    gross_pay = gross_pay_base * gross_pay_multiplier
    gross_year_to_date = float(gross_to_date) or (gross_year_to_date + gross_pay)

    for deduction in deductions:
        exec(f"{deduction['abbr']} = 0.0")

    for deduction in deductions:
        component_name_abbr_matrix[deduction['abbr']] = deduction['salary_component']
        value = 0.00
        if not deduction['amount_based_on_formula']:
            value = deduction['amount']

        else:
            if deduction['formula']:
                value = float(eval(deduction['formula'].replace("\n", " ")))

        exec(f"{deduction['abbr']} = {str(value)}")
        deductions_matrix[deduction['abbr']] = value

        if not deduction['do_not_include_in_total'] and not deduction["statistical_component"]:
            deductions_total = deductions_total + value

    return frappe.render_template(
        "erpusa/templates/html/test_pay_slip.html",
        {
            "gross_pay_base": gross_pay_base,
            "gross_pay": gross_pay,
            "payroll_frequency": payroll_frequency,
            "gross_pay_multiplier": gross_pay_multiplier,
            "earnings": earnings_matrix,
            "deductions": deductions_matrix,
            "earnings_total": earnings_total, 
            "deductions_total": deductions_total, 
            "component_name_abbr_matrix": component_name_abbr_matrix
        }
    )

@frappe.whitelist()
def test_salary_slip(docname, start_date, end_date, override_gross_ytd=None):
    assignment = frappe.get_doc("Salary Structure Assignment", docname)

    slip = frappe.get_doc({
        "doctype": "Salary Slip",
        "employee": assignment.employee,
        "salary_structure": assignment.salary_structure,
        "company": assignment.company,
        "start_date": getdate(start_date),
        "end_date": getdate(end_date),
        "payroll_frequency": frappe.db.get_value("Salary Structure", assignment.salary_structure, "payroll_frequency")
    })

    slip.run_method("fill_salary_structure")
    frappe.throw(str(slip.as_dict()))

    # Optional override
    if override_gross_ytd:
        slip.gross_year_to_date = float(override_gross_ytd)

        frappe.throw(str(slip.gross_year_to_date))
        # Re-run calculation if needed
        slip.calculate_net_pay()

    result = {
        "earnings": [{"component": e.salary_component, "amount": e.amount} for e in slip.earnings],
        "deductions": [{"component": d.salary_component, "amount": d.amount} for d in slip.deductions],
        "net_pay": slip.net_pay,
        "gross_ytd_used": slip.gross_year_to_date
    }

    return result

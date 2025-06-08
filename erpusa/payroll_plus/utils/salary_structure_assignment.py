import frappe
from frappe import _
from hrms.payroll.doctype.salary_structure.salary_structure import make_salary_slip
from frappe.utils import (
	getdate, add_years
)
from datetime import datetime
from hrms.payroll.doctype.payroll_entry.payroll_entry import get_end_date, get_start_end_dates

@frappe.whitelist()
def test_salary_slip_printable(
    salary_structure_assignment,
    salary_structure,
    employee,
    company,
    gross_to_date=None,
    base=None,
    variable=None,
    start_date=None,
    end_date=None
):
    
    if float(gross_to_date) < 0.0 or float(base) < 0.0 or float(variable) < 0.0:
        frappe.throw(_("Negative values are not allowed."))

    base = float(base)
    variable = float(variable)
    gross_year_to_date = 0.00
    gross_pay = 0.00
    payroll_frequency = frappe.db.get_value("Salary Structure", salary_structure, "payroll_frequency")
    
    if not end_date:
        dates = get_start_end_dates(payroll_frequency, start_date)
        start_date, end_date = dates["start_date"], dates["end_date"]
    
    else:
        start_date = datetime.strptime(start_date, "%Y-%m-%d")
        end_date = datetime.strptime(end_date, "%Y-%m-%d")

    if frappe.db.count("Salary Slip", filters={"employee": employee}):
        start_date_a_year_ago = add_years(start_date, -1)

        salary_slips = frappe.get_all(
            "Salary Slip",
            filters={
                "end_date": ["between", [start_date_a_year_ago, start_date]],
                "employee": employee
            },
            pluck="gross_pay"
        )

        gross_year_to_date = sum(salary_slips)

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

    earnings_matrix = []
    deductions_matrix = []
    earnings_total = 0.0
    deductions_total = 0.0

    for earning in earnings:
        exec(f"{earning['abbr']} = 0.0")

    for earning in earnings:
        value = 0.00
        if not earning['amount_based_on_formula']:
            value = float(earning['amount'])

        else:
            if earning['formula']:
                value = float(eval(earning['formula'].replace("\n", " ")))

        exec(f"{earning['abbr']} = {str(value)}")

        earnings_matrix.append({
            "abbr": earning['abbr'],
            "value": value,
            "name": earning['salary_component'],
            "formula": earning['formula'].replace("\n", "</br>")
        })

        if not earning['do_not_include_in_total'] and not earning["statistical_component"]:
            gross_pay = gross_pay + value
            earnings_total = earnings_total + value

    gross_year_to_date = float(gross_to_date) or (gross_year_to_date + gross_pay)

    for deduction in deductions:
        exec(f"{deduction['abbr']} = 0.0")

    for deduction in deductions:
        value = 0.00
        if not deduction['amount_based_on_formula']:
            value = deduction['amount']

        else:
            if deduction['formula']:
                value = float(eval(deduction['formula'].replace("\n", " ")))

        exec(f"{deduction['abbr']} = {str(value)}")

        deductions_matrix.append({
            "abbr": deduction['abbr'],
            "value": value,
            "name": deduction['salary_component'],
            "formula": deduction['formula'].replace("\n", "</br>")
        })

        if not deduction['do_not_include_in_total'] and not deduction["statistical_component"]:
            deductions_total = deductions_total + value

    return frappe.render_template(
        "erpusa/templates/html/test_pay_slip.html",
        {
            "employee": employee,
            "company": company,
            "base": base,
            "payroll_frequency": payroll_frequency,
            "start_date": start_date.strftime("%m-%d-%Y"),
            "end_date": end_date.strftime("%m-%d-%Y"),
            "working_days": frappe.utils.date_diff(end_date, start_date) + 1,
            "payment_days": frappe.utils.date_diff(end_date, start_date) + 1,
            "earnings": earnings_matrix,
            "deductions": deductions_matrix,
            "earnings_total": earnings_total, 
            "deductions_total": deductions_total,
        }
    )

@frappe.whitelist()
def get_end_date_from_start_date(start_date, salary_structure):
    payroll_frequency = frappe.db.get_value("Salary Structure", salary_structure, "payroll_frequency")

    return get_end_date(start_date, payroll_frequency)

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

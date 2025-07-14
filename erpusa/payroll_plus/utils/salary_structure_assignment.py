import frappe
from hrms.payroll.doctype.salary_structure.salary_structure import make_salary_slip
from frappe.model.mapper import get_mapped_doc
from frappe.utils import cint, cstr, flt

@frappe.whitelist()
def test_salary_slip(
    source_name,
    employee,
    posting_date,
    print_format,
    target_doc=None,
    gross_to_date=None,
    base=None,
    variable=None,
    start_date=None,
    end_date=None
):
    def postprocess(source, target):
        if employee:
            target.employee = employee
            if posting_date:
                target.posting_date = posting_date

        target.start_date = start_date
        target.end_date = end_date

        target.run_method("process_salary_structure", for_preview=True)
        target.gross_pay = float(base)
        target.base_gross_pay = float(base)
        target.run_method("calculate_net_pay")

    doc = get_mapped_doc(
        "Salary Structure",
        source_name,
        {
            "Salary Structure": {
                "doctype": "Salary Slip",
                "field_map": {
                    "total_earning": "gross_pay",
                    "name": "salary_structure",
                    "currency": "currency",
                },
            }
        },
        target_doc,
        postprocess,
        ignore_child_tables=True,
        cached=True,
    )

    frappe.throw(str(doc._salary_structure_doc.as_dict()))

    doc.name = f"Preview for {employee}"
    return frappe.get_print(doc.doctype, doc.name, doc=doc, print_format=print_format)
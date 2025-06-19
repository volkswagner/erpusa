import frappe

from hrms.payroll.doctype.salary_slip.salary_slip import SalarySlip
from frappe.utils import call_hook_method, cint, flt, get_url
from erpusa.payroll_plus.utils.salary_structure_assignment import get_prev_gross_ytd

class SalarySlipOverride(SalarySlip):
    @frappe.whitelist()
    def get_emp_and_working_day_details(self):
        """First time, load all the components from salary structure"""
        if self.employee:
            self.set("prev_gross_ytd", get_prev_gross_ytd(self.employee)) 
            self.set("earnings", [])
            self.set("deductions", [])

            if not self.salary_slip_based_on_timesheet:
                self.get_date_details()

            self.validate_dates()

            # getin leave details
            self.get_working_days_details()
            struct = self.check_sal_struct()

            if struct:
                self.set_salary_structure_doc()
                self.salary_slip_based_on_timesheet = (
                    self._salary_structure_doc.salary_slip_based_on_timesheet or 0
                )
                self.set_time_sheet()
                self.pull_sal_struct()
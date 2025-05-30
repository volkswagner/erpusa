app_name = "erpusa"
app_title = "ERPUSA"
app_publisher = "VolksWagner"
app_description = "An add-on to ERPNext that tailors and expands features more suitable for American users and companies."
app_email = "apps@itgetit.com"
app_license = "mit"

# Apps
# ------------------

required_apps = [
    "erpnext",
    "payments"
]

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "erpusa",
# 		"logo": "/assets/erpusa/logo.png",
# 		"title": "ERPUSA",
# 		"route": "/erpusa",
# 		"has_permission": "erpusa.api.permission.has_app_permission"
# 	}
# ]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/erpusa/css/erpusa.css"

# include js, css files in header of web template
# web_include_css = "/assets/erpusa/css/erpusa.css"
# web_include_js = "/assets/erpusa/js/erpusa.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "erpusa/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
doctype_js = {
    "Payment Request" : "public/js/payment_request.js",
    "Payment Entry" : "public/js/payment_entry.js",
	"Customer" : "public/js/customer.js",
}
doctype_list_js = {
    "Sales Invoice" : "public/js/sales_invoice_list.js"
}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "erpusa/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "erpusa.utils.jinja_methods",
# 	"filters": "erpusa.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "erpusa.install.before_install"
after_install = "erpusa.post_installation.create_docs.create_docs_payment_methods"

# Uninstallation
# ------------

# before_uninstall = "erpusa.uninstall.before_uninstall"
# after_uninstall = "erpusa.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "erpusa.utils.before_app_install"
# after_app_install = "erpusa.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "erpusa.utils.before_app_uninstall"
# after_app_uninstall = "erpusa.utils.after_app_uninstall"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "erpusa.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# DocType Class
# ---------------
# Override standard doctype classes

override_doctype_class = {
	"Stripe Settings": "erpusa.stripe_plus.overrides.stripe_settings_override.StripeSettingsOverride"
}

# Document Events
# ---------------
# Hook on document methods and events

doc_events = {
	"Payment Request": {
        "validate": "erpusa.stripe_plus.doctype.stripe_plus_settings.stripe_plus_settings.validate_stripe_plus_fields"
	}
}

# Scheduled Tasks
# ---------------

scheduler_events = {
	# "all": [
	# 	"erpusa.tasks.all"
	# ],
	# "daily": [
	#	"erpusa.tasks.daily"
	# ],
	# "hourly": [
	# 	"erpusa.tasks.hourly"
	# ],
	# "weekly": [
	# 	"erpusa.tasks.weekly"
	# ],
	# "monthly": [
	# 	"erpusa.tasks.monthly"
	# ],
	"cron": {
        "* * * * *": [
            "erpusa.stripe_plus.hook.minutely_task.send_daily_digest"
        ]
    }
}

# Testing
# -------

# before_tests = "erpusa.install.before_tests"

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "erpusa.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "erpusa.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["erpusa.utils.before_request"]
# after_request = ["erpusa.utils.after_request"]

# Job Events
# ----------
# before_job = ["erpusa.utils.before_job"]
# after_job = ["erpusa.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"erpusa.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

# fixtures = [
#     "Custom Field",
#     "Property Setter",
#     "Custom DocPerm"
# ]

fixtures = [
       {
         "dt": "Custom Field", 
         "filters":[
             [
                "module", "in", ["Stripe Plus", "ERPUSA"]
			 ]
        ]
      },
]

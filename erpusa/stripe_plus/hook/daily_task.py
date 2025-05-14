import frappe
import datetime
import urllib


def generate_digest_notification_message(schedule_info):
    count = frappe.db.count(
        "Merchant Payment", 
        filters={
            "created": ["between", [ schedule_info["date_start"], schedule_info["date_end"] ] ]
        }
    )
    schedule = schedule_info["schedule_time"]
    
    dt_format = "%Y-%m-%d %H:%M:%S"
    date_start_parameter = urllib.parse.quote(f'[">=","{schedule_info["date_start"].strftime(dt_format)}"]', safe='')
    date_end_parameter = urllib.parse.quote(f'["<=","{schedule_info["date_end"].strftime(dt_format)}"]', safe='')
    list_url = frappe.utils.get_url() + f"/app/merchant-payment?created={date_start_parameter}&created_before={date_end_parameter}"

    return frappe.render_template(
        "erpusa/templates/html/daily_digest.html",
        {
            "count": count,
            "schedule": schedule,
            "list_url": list_url,
        },
    )

@frappe.whitelist()
def find_schedule_date_ranges():
    schedules = frappe.get_all("Stripe Plus Settings Notification Schedule", pluck="time", order_by="time asc")
    schedule_labels = frappe.get_all("Stripe Plus Settings Notification Schedule", pluck="label", order_by="time asc")
    today = datetime.datetime.combine(datetime.date.today(), datetime.time.min)
    yesterday = today - datetime.timedelta(days=1)

    datetimes = [today + td for td in schedules]

    gap_ranges = []
    for i in range(len(datetimes) - 1):
        gap_start = datetimes[i] + datetime.timedelta(seconds=1)
        gap_end = datetimes[i + 1]
        gap_ranges.append({
            "date_start": gap_start, 
            "date_end": gap_end,
            "schedule_time": schedules[i + 1],
            "label": schedule_labels[i + 1]
        })

    first_gap = {
        "date_start": yesterday + schedules[-1] + datetime.timedelta(seconds=1),
        "date_end": datetimes[0],
        "schedule_time": schedules[0],
        "label": schedule_labels[0]
    }
    gap_ranges.insert(0, first_gap)

    return gap_ranges

def create_scheduled_notifications():
    schedules_detailed = find_schedule_date_ranges()
    recipients = frappe.db.get_single_value("Stripe Plus Settings", "notification_recipients")

    for schedule in schedules_detailed:
        if not frappe.db.exists("Email Queue", {"send_after": schedule["date_end"]}):
            label = schedule["label"] if schedule["label"] else schedule["date_end"].strftime("%H:%M")
            frappe.sendmail(
                recipients=recipients.split(),
                subject=f"Your {label} daily digest",
                message=generate_digest_notification_message(schedule),
                send_after=schedule["date_end"]
            )
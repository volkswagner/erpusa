import frappe
import datetime
import urllib


def generate_digest_notification_message(schedule_info, description):
    dt_format = "%Y-%m-%d %H:%M:%S"
    date_start_parameter = urllib.parse.quote(f'[">=","{schedule_info["date_start"].strftime(dt_format)}"]', safe='')
    date_end_parameter = urllib.parse.quote(f'["<=","{schedule_info["date_end"].strftime(dt_format)}"]', safe='')
    list_url = frappe.utils.get_url() + f"/app/merchant-payment?created={date_start_parameter}&created_before={date_end_parameter}"

    return frappe.render_template(
        "erpusa/templates/html/daily_digest.html",
        {
            "description": description,
            "list_url": list_url
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

def send_daily_digest():
    now = datetime.datetime.now()
    now_time = now.replace(second=0, microsecond=0)
    midnight = datetime.datetime.combine(now.date(), datetime.time.min)
    time_today = now_time - midnight
    time_today = datetime.timedelta(days=time_today.days, hours=time_today.seconds // 3600, minutes=(time_today.seconds % 3600) // 60)
    schedules = frappe.get_all("Stripe Plus Settings Notification Schedule", pluck="time", order_by="time asc")
    if frappe.db.get_single_value("Stripe Plus Settings", "turn_on_email_notifications"):
        if frappe.db.get_single_value("Stripe Plus Settings", "notification_method") == "Daily Digest":
            if time_today in schedules:
                schedules_detailed = find_schedule_date_ranges()
                schedule_index = schedules.index(time_today)
                schedule_detail = schedules_detailed[schedule_index]
                count = frappe.db.count(
                    "Merchant Payment", 
                    filters={
                        "created": ["between", [ schedule_detail["date_start"], schedule_detail["date_end"] ] ]
                    }
                )
                if count:
                    recipients = frappe.db.get_single_value("Stripe Plus Settings", "notification_recipients")
                    label = schedule_detail["label"] if schedule_detail["label"] else schedule_detail["date_end"].strftime("%H:%M")
                    
                    if schedule_index == 0:
                        description = f'You have <b id="count">{count}</b> new transaction(s) that occurred before {schedule_detail["date_end"].strftime("%H:%M")}'
                    else:
                        description = f'You have <b id="count">{count}</b> new transaction(s) since the last digest'
                    
                    
                    frappe.sendmail(
                        recipients=recipients.split(),
                        subject=f"Your {label} daily digest",
                        message=generate_digest_notification_message(
                            schedule_detail,
                            description
                        ),
                        now=True
                    )
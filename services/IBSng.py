import re

import requests
from bs4 import BeautifulSoup

from config import IBS_USERNAME, IBS_PASSWORD, IBS_URL_BASE, IBS_URL_INFO, IBS_URL_EDIT, IBS_URL_CONNECTIONS, \
    IBS_URL_DELETE


def login():
    # Create a session to persist cookies
    session = requests.Session()

    # Define the payload for the login form
    payload = {
        'username': IBS_USERNAME,
        'password': IBS_PASSWORD
    }
    # Perform the login request
    response = session.post(IBS_URL_BASE, data=payload)
    # Check if the login was successful
    if response.ok:
        return session
    else:
        print("Login failed!")


def get_user_id(username):
    session = login()
    user_info_url = IBS_URL_INFO
    payload = {
        'normal_username_multi': username
    }
    response = session.post(user_info_url, data=payload)
    if response.ok:
        soup = BeautifulSoup(response.text, 'html.parser')

        # Find all 'tr' elements
        tr_elements = soup.find_all('tr')

        # Initialize variable to store User ID
        user_id = None

        # Iterate through the rows to find the User ID
        for tr in tr_elements:
            # Find the 'td' elements in this row
            td_elements = tr.find_all('td')

            # Check if the row contains 'User ID'
            if len(td_elements) > 2 and 'User ID' in td_elements[1].get_text():
                # Extract the user ID from the next 'td' element
                user_id = td_elements[2].get_text().strip()
                break

        if user_id:
            return user_id
        else:
            print("User ID not found")
            return None


def get_user_exp_date(username):
    session = login()
    user_id = get_user_id(username)
    # user_info_url = 'http://ibs.persiapro.com/IBSng/admin/user/user_info.php'
    user_info_url = IBS_URL_INFO

    payload = {
        'user_id_multi': user_id
    }
    response = session.post(user_info_url, data=payload)
    if response.ok:
        soup = BeautifulSoup(response.text, 'html.parser')

        # Find all 'tr' elements
        tr_elements = soup.find_all('tr')

        # Initialize variable to store User ID
        user_exp_date = None

        # Iterate through the rows to find the User ID
        for tr in tr_elements:
            # Find the 'td' elements in this row
            td_elements = tr.find_all('td')

            # Check if the row contains 'User ID'
            if len(td_elements) > 2 and 'Nearest Expiration Date' in td_elements[1].get_text():
                # Extract the user ID from the next 'td' element
                user_exp_date = td_elements[2].get_text().strip()
                break

        if user_exp_date:
            if user_exp_date == "---------------":
                return None
            else:
                return user_exp_date
        else:
            print("Nearest Expiration Date not found")
            return None


def get_user_start_date(username):
    session = login()
    user_id = get_user_id(username)
    # user_info_url = 'http://ibs.persiapro.com/IBSng/admin/user/user_info.php'
    user_info_url = IBS_URL_INFO

    payload = {
        'user_id_multi': user_id
    }
    response = session.post(user_info_url, data=payload)
    if response.ok:
        soup = BeautifulSoup(response.text, 'html.parser')

        # Find all 'tr' elements
        tr_elements = soup.find_all('tr')

        # Initialize variable to store User ID
        user_first_login = None
        # Iterate through the rows to find the User ID
        for tr in tr_elements:
            # Find the 'td' elements in this row
            td_elements = tr.find_all('td')

            # Check if the row contains 'User ID'
            if len(td_elements) > 2 and 'First Login' in td_elements[1].get_text():
                # Extract the user ID from the next 'td' element
                user_first_login = td_elements[2].get_text().strip()
                break
        if user_first_login:
            if user_first_login == "---------------":
                return None
            else:
                return user_first_login
        else:
            return None


def user_info_page(user_id):
    session = login()
    # user_info_url = 'http://ibs.persiapro.com/IBSng/admin/user/user_info.php'
    user_info_url = IBS_URL_INFO

    payload = {
        'user_id_multi': user_id
    }
    response = session.post(user_info_url, data=payload)
    if response.ok:
        print("Data fetched successfully!")
        return response
    else:
        print("Failed to fetch data.")
        print("Status code:", response.status_code)
        print("Response:", response.text)
        return None


def change_group(username, group):
    session = login()
    user_id = get_user_id(username)
    # edit_url = 'http://ibs.persiapro.com/IBSng/admin/plugins/edit.php'
    edit_url = IBS_URL_EDIT
    payload = {
        'target': 'user',
        'target_id': user_id,
        'update': '1',
        'edit_tpl_cs': 'group_name',
        'attr_update_method_0': 'groupName',
        'group_name': group
    }
    session.post(edit_url, data=payload)


def change_password(username, password):
    session = login()
    user_id = get_user_id(username)
    # edit_url = 'http://ibs.persiapro.com/IBSng/admin/plugins/edit.php'
    edit_url = IBS_URL_EDIT

    payload = {
        'target': 'user',
        'target_id': user_id,
        'update': '1',
        'edit_tpl_cs': 'normal_username',
        'attr_update_method_0': 'normalAttrs',
        'has_normal_username': 't',
        'current_normal_username': username,
        'normal_username': username,
        'password_character': 't',
        'password_digit': 't',
        'password_len': '6',
        'password': password
    }
    response = session.post(edit_url, data=payload)
    if response.ok:
        print("Password Changed successfully!")
    else:
        print("Failed to Change Password.")
        print("Status code:", response.status_code)


def lock_user(username):
    session = login()
    user_id = get_user_id(username)
    # edit_url = 'http://ibs.persiapro.com/IBSng/admin/plugins/edit.php'
    edit_url = IBS_URL_EDIT

    payload = {
        'target': 'user',
        'target_id': user_id,
        'update': '1',
        'edit_tpl_cs': 'lock',
        'tab1_selected': 'Main',
        'attr_update_method_0': 'lock',
        'has_lock': 't',
        'lock': ''
    }
    response = session.post(edit_url, data=payload)
    if response.ok:
        print("User has been locked!")
    else:
        print("Failed to lock the user.")
        print("Status code:", response.status_code)


def unlock_user(username):
    session = login()
    user_id = get_user_id(username)
    # edit_url = 'http://ibs.persiapro.com/IBSng/admin/plugins/edit.php'
    edit_url = IBS_URL_EDIT
    payload = {
        'target': 'user',
        'target_id': user_id,
        'update': '1',
        'edit_tpl_cs': 'lock',
        'tab1_selected': 'Main',
        'attr_update_method_0': 'lock',
    }
    session.post(edit_url, data=payload)


def reset_first_login(username):
    session = login()
    user_id = get_user_id(username)
    edit_url = IBS_URL_EDIT

    payload = {
        'target': 'user',
        'target_id': user_id,
        'update': '1',
        'edit_tpl_cs': 'first_login',
        'tab1_selected': 'Exp_Dates',
        'attr_update_method_0': 'firstLogin',
        'reset_first_login': 't',
    }
    response = session.post(edit_url, data=payload)

    if response.ok:
        print("User expire time has been reset!")
    else:
        print("Failed to reset user expire time.")
        print("Status code:", response.status_code)


def kill_user(user_id, username):
    session = login()
    # edit_url = 'http://ibs.persiapro.com/IBSng/admin/user/kill_user.php'
    edit_url = IBS_URL_EDIT
    url = 'http://ibs.persiapro.com/IBSng/admin/report/online_users.php'
    response = session.get(url)
    print(response.text)

    payload = {
        'user_id': user_id,
        'username': username,
        # 'ras_ip': ras_ip,
        # 'unique_id_val': unique_id_val,
        'kill': '1'
    }
    response = session.post(edit_url, data=payload)
    if response.ok:
        print("User expire time has been reset!")
    else:
        print("Failed to reset user expire time.")
        print("Status code:", response.status_code)


def get_user_password(user_id):
    session = login()
    # edit_url = 'http://ibs.persiapro.com/IBSng/admin/plugins/edit.php'
    edit_url = IBS_URL_EDIT
    payload = {
        'user_id': user_id,
        'edit_user': '1',
        'attr_edit_checkbox_2': 'normal_username',
    }
    response = session.post(edit_url, data=payload)
    if response.ok:
        print(response.text)
        soup = BeautifulSoup(response.text, 'html.parser')

        # Find all 'tr' elements
        tr_elements = soup.find_all('tr')

        # Initialize variable to store User ID
        password = None
        # Iterate through the rows to find the User ID
        for tr in tr_elements:
            # Find the 'td' elements in this row
            td_elements = tr.find_all('td')

            # Check if the row contains 'User ID'
            if len(td_elements) > 2 and 'Password:' in td_elements[1].get_text():
                # Extract the user ID from the next 'td' element
                password = td_elements[2].get_text().strip()
                break
        if password:
            return password
        else:
            return None


def reset_relative_exp_date(username):
    session = login()
    user_id = get_user_id(username)
    # edit_url = 'http://ibs.persiapro.com/IBSng/admin/plugins/edit.php'
    edit_url = IBS_URL_EDIT
    payload = {
        'target': 'user',
        'target_id': user_id,
        'update': '1',
        'edit_tpl_cs': 'rel_exp_date',
        'tab1_selected': 'Exp_Dates',
        'attr_update_method_0': 'relExpDate'
    }
    response = session.post(edit_url, data=payload)

    if response.ok:
        print("User relative expire time has been reset!")
    else:
        print("Failed to reset user relative expire time.")
        print("Status code:", response.status_code)


def reset_times(username):
    session = login()
    user_id = get_user_id(username)
    # edit_url = 'http://ibs.persiapro.com/IBSng/admin/plugins/edit.php'
    edit_url = IBS_URL_EDIT

    payload = {
        'target': 'user',
        'target_id': user_id,
        'update': '1',
        'edit_tpl_cs': 'rel_exp_date,abs_exp_date,first_login',
        'tab1_selected': 'Exp_Dates',
        'attr_update_method_0': 'relExpDate',
        'attr_update_method_1': 'absExpDate',
        'attr_update_method_2': 'firstLogin',
        'reset_first_login': 't',
    }
    session.post(edit_url, data=payload)


def reset_radius_attrs(username):
    session = login()
    user_id = get_user_id(username)
    # edit_url = 'http://ibs.persiapro.com/IBSng/admin/plugins/edit.php'
    edit_url = IBS_URL_EDIT

    payload = {
        'target': 'user',
        'target_id': user_id,
        'update': '1',
        'edit_tpl_cs': 'radius_attrs',
        'tab1_selected': 'Misc',
        'attr_update_method_0': 'radiusAttrs',
    }
    session.post(edit_url, data=payload)


def reset_account(username):
    reset_times(username)
    change_group(username, 'Starter')
    unlock_user(username)
    reset_radius_attrs(username)


def reset_account_client(username):
    reset_times(username)
    change_group(username, 'Starter-Bot')
    unlock_user(username)
    reset_radius_attrs(username)


def get_usage_last_n_days(username, days):
    session = login()
    user_id = get_user_id(username)
    # user_info_url = 'http://ibs.persiapro.com/IBSng/admin/report/connections.php'
    user_info_url = IBS_URL_CONNECTIONS
    payload = {
        'show_reports': 1,
        'page': 1,
        'admin_connection_logs': 1,
        'user_ids': user_id,
        'owner': 'All',
        'login_time_from': days,
        'login_time_from_unit': 'days',
        'login_time_to_unit': 'days',
        'show_total_duration': 'on',
        'show_total_inouts': 'on',
        'successful_yes': 'on',
        'order_by': 'login_time',
        'rpp': 20
    }
    response = session.post(user_info_url, data=payload)
    if response.ok:
        soup = BeautifulSoup(response.text, 'html.parser')

        # Find all <td> elements
        td_elements = soup.find_all('td', class_='list_col')

        # Initialize variables for the values
        receive = None
        send = None

        # Iterate through <td> elements to find the desired values
        for td in td_elements:

            # Check for "Report Total In Bytes" label
            if "Report" in td.text and "Total In Bytes:" in td.text:
                receive = td.find_next_sibling('td').text.strip()

            # Check for "Report Total Out Bytes" label
            elif "Report" in td.text and "Total Out Bytes:" in td.text:
                send = td.find_next_sibling('td').text.strip()

        return receive, send
    return None, None


def delete_user(username):
    session = login()
    user_id = get_user_id(username)
    # delete_url = 'http://ibs.persiapro.com/IBSng/admin/user/del_user.php'
    delete_url = IBS_URL_DELETE
    payload = {
        'user_id': user_id,
        'delete': '1',
        'delete_comment': '',
        'delete_connection_logs': 'on',
        'delete_audit_logs': 'on'
    }
    response = session.post(delete_url, data=payload)

    if response.ok:
        print(f"User {username} has been deleted!")
    else:
        print("Failed to delete user.")
        print("Status code:", response.status_code)


def change_queue_level(username, queue_level):
    """

    levels = {
        1: "Rate-Limit=\"0/6m 0/8m 0/1m 0/4\"",
        2: "Rate-Limit=\"0/4m 0/6m 0/1m 0/4\"",
        3: "Rate-Limit=\"0/2m 0/4m 0/1m 0/4\"",
    }
    """
    levels = {
        1: "Rate-Limit=\"4m/4m\"",
        2: "Rate-Limit=\"2m/2m\"",
        3: "Rate-Limit=\"1m/1m\"",
    }
    session = login()
    user_id = get_user_id(username)
    # edit_url = 'http://ibs.persiapro.com/IBSng/admin/plugins/edit.php'
    edit_url = IBS_URL_EDIT
    if queue_level == 0:
        payload = {
            'target': 'user',
            'target_id': user_id,
            'update': '1',
            'edit_tpl_cs': 'radius_attrs',
            'tab1_selected': 'Misc',
            'attr_update_method_0': 'radiusAttrs',
            'has_radius_attrs': 'f',
        }
    else:
        payload = {
            'target': 'user',
            'target_id': user_id,
            'update': '1',
            'edit_tpl_cs': 'radius_attrs',
            'tab1_selected': 'Misc',
            'attr_update_method_0': 'radiusAttrs',
            'has_radius_attrs': 't',
            'radius_attrs': levels[queue_level]
        }
    response = session.post(edit_url, data=payload)
    if not response.ok:
        print("Failed to change queue level.")
        print("Status code:", response.status_code)


def apply_user_radius_attrs(username, radius_attrs):
    session = login()
    user_id = get_user_id(username)
    # edit_url = 'http://ibs.persiapro.com/IBSng/admin/plugins/edit.php'
    edit_url = IBS_URL_EDIT
    payload = {
        'target': 'user',
        'target_id': user_id,
        'update': '1',
        'edit_tpl_cs': 'radius_attrs',
        'tab1_selected': 'Misc',
        'attr_update_method_0': 'radiusAttrs',
        'has_radius_attrs': 't',
        'radius_attrs': radius_attrs
    }
    session.post(edit_url, data=payload)


def get_user_radius_attribute(username):
    session = login()
    user_id = get_user_id(username)
    user_info_url = IBS_URL_INFO
    payload = {
        'user_id_multi': user_id
    }
    response = session.post(user_info_url, data=payload)
    if response.ok:
        soup = BeautifulSoup(response.text, 'html.parser')

        # پیدا کردن تگ td که مقدار Radius Attributes را دارد
        tds = soup.find_all("td", class_="Form_Content_Row_Right_textarea_td_dark")
        for td in tds:
            if "Group=" in td.text or "Rate-Limit=" in td.text or "Mikrotik-Rate-Limit=" in td.text:
                content = td.get_text(strip=True, separator="\n")
                # استخراج کلید-مقدارها با regex
                attributes = dict(re.findall(r'([A-Za-z\-]+)="([^"]+)"', content))
                return attributes  # خروج از تابع بعد از پیدا کردن اولین td معتبر

    return None  # اگر چیزی پیدا نشد


def get_group_radius_attribute(username):
    session = login()
    user_id = get_user_id(username)
    user_info_url = IBS_URL_INFO
    payload = {
        'user_id_multi': user_id
    }
    response = session.post(user_info_url, data=payload)
    group_name = ""
    if response.ok:
        soup = BeautifulSoup(response.text, 'html.parser')

        link = soup.find("a", href=re.compile(r"group_info\.php\?group_name="))
        if link:
            group_name = link.text.strip()

    edit_url = IBS_URL_EDIT
    payload = {
        'group_name': group_name,
        'edit_group': '1',
        'attr_edit_checkbox_18': 'radius_attrs',
    }

    response = session.post(edit_url, data=payload)
    if response.ok:
        soup = BeautifulSoup(response.text, 'html.parser')
        # پیدا کردن تگ td که مقدار Radius Attributes را دارد
        tds = soup.find_all("td", class_="Form_Content_Row_Right_textarea_td_dark")
        for td in tds:
            if "Group=" in td.text or "Rate-Limit=" in td.text or "Mikrotik-Rate-Limit=" in td.text:
                content = td.get_text(strip=True, separator="\n")
                # استخراج کلید-مقدارها با regex
                attributes = dict(re.findall(r'([A-Za-z\-]+)="([^"]+)"', content))
                return attributes  # خروج از تابع بعد از پیدا کردن اولین td معتبر

    return None  # اگر چیزی پیدا نشد


def temporary_charge(username):
    session = login()
    user_id = get_user_id(username)

    payload = {
        'target': 'user',
        'target_id': user_id,
        'update': '1',
        'edit_tpl_cs': 'rel_exp_date,abs_exp_date,first_login',
        'tab1_selected': 'Exp_Dates',
        'attr_update_method_0': 'relExpDate',
        'attr_update_method_1': 'absExpDate',
        'attr_update_method_2': 'firstLogin',
        'reset_first_login': 't',
    }
    session.post(IBS_URL_EDIT, data=payload)

    payload = {
        'target': 'user',
        'target_id': user_id,
        'update': '1',
        'edit_tpl_cs': 'group_name',
        'attr_update_method_0': 'groupName',
        'group_name': '1-Hour'
    }
    session.post(IBS_URL_EDIT, data=payload)

    payload = {
        'target': 'user',
        'target_id': user_id,
        'update': '1',
        'edit_tpl_cs': 'lock',
        'tab1_selected': 'Main',
        'attr_update_method_0': 'lock',
    }
    session.post(IBS_URL_EDIT, data=payload)

    payload = {
        'target': 'user',
        'target_id': user_id,
        'update': '1',
        'edit_tpl_cs': 'radius_attrs',
        'tab1_selected': 'Misc',
        'attr_update_method_0': 'radiusAttrs',
    }
    session.post(IBS_URL_EDIT, data=payload)


def get_usage_from_ibs(username, starts_at, expires_at):
    session = login()
    user_id = get_user_id(username)
    payload = {
        'show_reports': 1,
        'page': 1,
        'admin_connection_logs': 1,
        'user_ids': user_id,
        'owner': 'All',
        'login_time_from': starts_at,
        'login_time_from_unit': 'jalali',
        'login_time_to': expires_at,
        'login_time_to_unit': 'jalali',
        'show_total_duration': 'on',
        'show_total_inouts': 'on',
        'successful_yes': 'on',
        'order_by': 'login_time',
        'rpp': 20
    }
    response = session.post(IBS_URL_CONNECTIONS, data=payload)
    if response.ok:
        soup = BeautifulSoup(response.text, 'html.parser')

        # Find all <td> elements
        td_elements = soup.find_all('td', class_='list_col')

        # Initialize variables for the values
        receive = None
        send = None

        # Iterate through <td> elements to find the desired values
        for td in td_elements:

            # Check for "Report Total In Bytes" label
            if "Report" in td.text and "Total In Bytes:" in td.text:
                receive = td.find_next_sibling('td').text.strip()

            # Check for "Report Total Out Bytes" label
            elif "Report" in td.text and "Total Out Bytes:" in td.text:
                send = td.find_next_sibling('td').text.strip()

        def convert_to_mb(data_str):
            # Get the numeric part of the string
            num = float(data_str[:-1])
            unit = data_str[-1].upper()
            if unit == 'B':
                return 0
            if unit == 'K':
                return int(num / 1024)  # Convert KB to MB and then to an integer
            elif unit == 'M':
                return int(num)  # Already in MB, just convert to an integer
            elif unit == 'G':
                return int(num * 1024)  # Convert GB to MB and then to an integer
            else:
                raise ValueError(f"Unknown unit: {unit}")

        send_mb = convert_to_mb(send)
        receive_mb = convert_to_mb(receive)

        return send_mb, receive_mb
    return None

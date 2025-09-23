import re

import requests
from bs4 import BeautifulSoup

from config import IBS_USERNAME, IBS_PASSWORD, IBS_URL_BASE, IBS_URL_INFO, IBS_URL_EDIT


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


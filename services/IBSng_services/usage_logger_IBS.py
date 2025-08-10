import requests
from bs4 import BeautifulSoup


def login():
    # Define the URL and login credentials
    login_url = 'http://ibs.persiapro.com/IBSng/admin/'
    username = 'system'
    password = 'Kent228mud120'

    # Create a session to persist cookies
    session = requests.Session()

    # Define the payload for the login form
    payload = {
        'username': username,
        'password': password
    }

    # Perform the login request
    response = session.post(login_url, data=payload)
    # Check if the login was successful
    if response.ok:
        return session
    else:
        print("Login failed!")
        print("Status code:", response.status_code)
        print("Response:", response.text)
        exit()


def get_user_id(username):
    session = login()
    user_info_url = 'http://ibs.persiapro.com/IBSng/admin/user/user_info.php'
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
    return None



def get_usage_from_ibs(username, starts_at, expires_at):
    session = login()
    user_id = get_user_id(username)
    user_info_url = 'http://ibs.persiapro.com/IBSng/admin/report/connections.php'
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


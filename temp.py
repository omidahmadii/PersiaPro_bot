from services.IBSng import get_user_radius_attribute, reset_radius_attrs

attr = get_user_radius_attribute("200001")
print(attr)


reset_radius_attrs("200001")

attr = get_user_radius_attribute("200001")
print(attr)

import sys
sys.path.insert(0, '.')

from fastapi import Response
from src.platform.api import _set_auth_cookies

response = Response()
_set_auth_cookies(response, "test_access_token", "test_refresh_token")

print(f"Response headers:")
for key, value in dict(response.headers).items():
    print(f"  {key}: {value}")
print(f"\nHas Set-Cookie: {'set-cookie' in response.headers}")
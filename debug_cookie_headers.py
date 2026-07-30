from fastapi import Response

response = Response()
response.set_cookie(key="test", value="value", httponly=True, secure=False, samesite="strict", max_age=3600)

print(f"Response headers: {dict(response.headers)}")
print(f"Has Set-Cookie: {'set-cookie' in response.headers}")
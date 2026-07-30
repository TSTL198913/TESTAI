from playwright.sync_api import sync_playwright

def debug_login_flow():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, slow_mo=500)
        context = browser.new_context()
        page = context.new_page()
        
        print("=== Navigating to login page ===")
        try:
            page.goto("http://localhost:3000/login", timeout=30000)
            print(f"Page URL: {page.url}")
            print(f"Page title: {page.title()}")
        except Exception as e:
            print(f"Failed to navigate: {e}")
            browser.close()
            return
        
        print("\n=== Checking page content ===")
        content = page.content()
        print(f"Content length: {len(content)}")
        
        print("\n=== Checking form fields ===")
        username_input = page.query_selector('input[name="username"]')
        password_input = page.query_selector('input[name="password"]')
        submit_button = page.query_selector('button[type="submit"]')
        
        print(f"Username input found: {username_input is not None}")
        print(f"Password input found: {password_input is not None}")
        print(f"Submit button found: {submit_button is not None}")
        
        if username_input and password_input and submit_button:
            print("\n=== Filling form ===")
            username_input.fill("admin")
            password_input.fill("password")
            
            print("\n=== Submitting form ===")
            with page.expect_response("**/auth/login") as response_info:
                submit_button.click()
            
            response = response_info.value
            print(f"\nLogin API Status: {response.status}")
            print(f"Login API URL: {response.url}")
            
            headers = response.headers
            print("\nResponse headers:")
            for key, value in headers.items():
                print(f"  {key}: {value}")
            
            body = response.text()
            print(f"\nResponse body: {body[:500]}")
            
            print("\n=== Checking cookies ===")
            cookies = context.cookies()
            print(f"Number of cookies: {len(cookies)}")
            for cookie in cookies:
                print(f"  {cookie['name']}: {cookie['value'][:50]}... (HttpOnly: {cookie.get('httpOnly', False)})")
            
            print("\n=== Checking localStorage ===")
            local_storage = page.evaluate("() => JSON.stringify(localStorage)")
            print(f"localStorage: {local_storage}")
            
            print("\n=== Waiting for redirect ===")
            try:
                page.wait_for_navigation(timeout=10000)
                print(f"Final URL: {page.url}")
            except Exception as e:
                print(f"No redirect: {e}")
                print(f"Current URL: {page.url}")
            
            print("\n=== Checking page after login ===")
            content_after = page.content()
            print(f"Content length after: {len(content_after)}")
        
        browser.close()

if __name__ == "__main__":
    debug_login_flow()

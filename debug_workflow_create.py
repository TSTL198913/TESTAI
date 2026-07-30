from playwright.sync_api import sync_playwright

chrome_path = "C:\\Users\\18907\\AppData\\Local\\Google\\Chrome\\Application\\chrome.exe"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, executable_path=chrome_path)
    page = browser.new_page()
    
    page.goto("http://localhost:3000/login")
    page.fill('input[id="username"]', "admin")
    page.fill('input[id="password"]', "password")
    page.click('button[type="submit"]')
    page.wait_for_load_state("networkidle")
    
    page.goto("http://localhost:3000/workflow")
    page.wait_for_load_state("networkidle")
    
    create_btn = page.locator('[data-testid="create-workflow-btn"]')
    create_btn.click()
    
    create_modal = page.locator('[data-testid="create-workflow-modal"]')
    print(f"Create modal visible: {create_modal.is_visible()}")
    
    name_input = page.locator('[data-testid="workflow-name-input"]')
    print(f"Name input found: {name_input.count() > 0}")
    
    if name_input.count() == 0:
        print("Looking for alternative input selectors...")
        inputs = page.locator("input")
        for i in range(inputs.count()):
            inp = inputs.nth(i)
            try:
                placeholder = inp.get_attribute("placeholder")
                id_attr = inp.get_attribute("id")
                print(f"Input {i}: id='{id_attr}', placeholder='{placeholder}'")
            except:
                pass
    
    browser.close()
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
    
    name_input = page.locator('[data-testid="workflow-name-input"]')
    workflow_name = "测试工作流_abc123"
    name_input.fill(workflow_name)
    print(f"Filled name: {workflow_name}")
    
    submit_btn = page.locator('[data-testid="workflow-submit-btn"]')
    print(f"Submit button found: {submit_btn.count() > 0}")
    
    if submit_btn.count() == 0:
        print("Looking for submit button alternatives...")
        buttons = page.locator("button")
        for i in range(buttons.count()):
            btn = buttons.nth(i)
            try:
                text = btn.inner_text()
                print(f"Button {i}: '{text}'")
            except:
                pass
    
    browser.close()
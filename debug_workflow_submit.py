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
    workflow_name = "测试工作流_debug001"
    name_input.fill(workflow_name)
    
    submit_btn = page.locator('[data-testid="workflow-submit-btn"]')
    submit_btn.click()
    
    page.wait_for_timeout(2000)
    
    cards = page.locator('[data-testid*="workflow-card-"]')
    print(f"Workflow cards found: {cards.count()}")
    
    for i in range(cards.count()):
        card = cards.nth(i)
        try:
            name_element = card.locator('[data-testid*="workflow-name-"]')
            if name_element.count() > 0:
                name_text = name_element.inner_text()
                print(f"Card {i}: '{name_text}'")
                if name_text == workflow_name:
                    print("FOUND THE WORKFLOW!")
        except:
            pass
    
    browser.close()
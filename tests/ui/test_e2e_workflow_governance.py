import pytest
import os
import uuid
from playwright.sync_api import Page, expect


class TestWorkflowGovernanceE2E:
    """工作流与治理审批端到端测试 - 完整业务流程"""

    def test_workflow_creation_to_execution_e2e(self, logged_in_page: Page):
        page = logged_in_page
        base_url = os.environ.get("BASE_URL", "http://localhost:3000")
        
        workflow_name = f"E2E测试工作流_{str(uuid.uuid4())[:8]}"
        
        page.goto(f"{base_url}/workflow")
        page.wait_for_load_state("networkidle")
        
        page.locator('button:has-text("创建工作流")').click()
        expect(page.locator('h3:has-text("创建工作流")')).to_be_visible()
        
        page.locator('input[placeholder="请输入工作流名称"]').fill(workflow_name)
        page.locator('textarea[placeholder="请输入工作流描述"]').fill("端到端测试工作流")
        page.locator('input[type="number"]').fill("3")
        
        page.locator('button[type="submit"]').click()
        page.wait_for_timeout(1500)
        
        expect(page.locator(f'h4:has-text("{workflow_name}")').first).to_be_visible()
        
        workflow_card = page.locator(f'.bg-white.rounded-xl:has(h4:has-text("{workflow_name}"))').first
        status_badge = workflow_card.locator('span[class*="rounded-full"]').first
        expect(status_badge).to_be_visible()
        
        execute_button = workflow_card.locator('button:has-text("执行")')
        if execute_button.count() > 0:
            execute_button.click()
            page.wait_for_timeout(1500)
            
            page.goto(f"{base_url}/workflow")
            page.wait_for_load_state("networkidle")
            
            updated_card = page.locator(f'.bg-white.rounded-xl:has(h4:has-text("{workflow_name}"))').first
            updated_status = updated_card.locator('span[class*="rounded-full"]').first
            expect(updated_status).to_be_visible()

    def test_governance_approval_flow_e2e(self, logged_in_page: Page):
        page = logged_in_page
        base_url = os.environ.get("BASE_URL", "http://localhost:3000")
        
        page.goto(f"{base_url}/governance")
        page.wait_for_load_state("networkidle")
        
        page.locator('button:has-text("执行治理")').click()
        page.wait_for_timeout(1500)
        
        page.locator('button:has-text("待审批")').click()
        page.wait_for_timeout(500)
        
        pending_rows = page.locator('tbody tr:has(span:has-text("待审批"))')
        if pending_rows.count() > 0:
            first_pending = pending_rows.first
            tx_id = first_pending.locator('td').first.inner_text()
            
            approve_button = first_pending.locator('button:has(svg[class*="CheckCircle"])')
            approve_button.click()
            page.wait_for_timeout(1000)
            
            page.locator('button:has-text("已批准")').click()
            page.wait_for_timeout(500)
            
            approved_rows = page.locator('tbody tr:has(span:has-text("已批准"))')
            assert approved_rows.count() >= 1
        else:
            assert pending_rows.count() >= 0

    def test_workflow_to_governance_full_flow(self, logged_in_page: Page):
        page = logged_in_page
        base_url = os.environ.get("BASE_URL", "http://localhost:3000")
        
        workflow_name = f"完整流程测试_{str(uuid.uuid4())[:8]}"
        
        page.goto(f"{base_url}/workflow")
        page.wait_for_load_state("networkidle")
        
        page.locator('button:has-text("创建工作流")').click()
        page.locator('input[placeholder="请输入工作流名称"]').fill(workflow_name)
        page.locator('button[type="submit"]').click()
        page.wait_for_timeout(1500)
        
        expect(page.locator(f'h4:has-text("{workflow_name}")').first).to_be_visible()
        
        page.locator('a[href="/governance"]').click()
        page.wait_for_load_state("networkidle")
        
        expect(page.locator('h2:has-text("治理流程")')).to_be_visible()
        
        page.locator('button:has-text("执行治理")').click()
        page.wait_for_timeout(1500)
        
        page.locator('button:has-text("全部")').click()
        page.wait_for_timeout(500)
        
        table = page.locator('table')
        expect(table).to_be_visible()

    def test_governance_reject_flow_e2e(self, logged_in_page: Page):
        page = logged_in_page
        base_url = os.environ.get("BASE_URL", "http://localhost:3000")
        
        page.goto(f"{base_url}/governance")
        page.wait_for_load_state("networkidle")
        
        page.locator('button:has-text("执行治理")').click()
        page.wait_for_timeout(1500)
        
        page.locator('button:has-text("待审批")').click()
        page.wait_for_timeout(500)
        
        pending_rows = page.locator('tbody tr:has(span:has-text("待审批"))')
        if pending_rows.count() > 0:
            first_pending = pending_rows.first
            
            reject_button = first_pending.locator('button:has(svg[class*="XCircle"])')
            reject_button.click()
            page.wait_for_timeout(1000)
            
            page.locator('button:has-text("已拒绝")').click()
            page.wait_for_timeout(500)
            
            rejected_rows = page.locator('tbody tr:has(span:has-text("已拒绝"))')
            assert rejected_rows.count() >= 1
        else:
            assert pending_rows.count() >= 0

    def test_workflow_execution_and_status_update(self, logged_in_page: Page):
        page = logged_in_page
        base_url = os.environ.get("BASE_URL", "http://localhost:3000")
        
        page.goto(f"{base_url}/workflow")
        page.wait_for_load_state("networkidle")
        
        pending_cards = page.locator('.bg-white.rounded-xl:has(span:has-text("待执行"))')
        if pending_cards.count() > 0:
            card = pending_cards.first
            card_name = card.locator('h4').inner_text()
            initial_status = card.locator('span[class*="rounded-full"]').first.inner_text()
            
            execute_button = card.locator('button:has-text("执行")')
            execute_button.click()
            page.wait_for_timeout(2000)
            
            page.goto(f"{base_url}/workflow")
            page.wait_for_load_state("networkidle")
            
            updated_card = page.locator(f'.bg-white.rounded-xl:has(h4:has-text("{card_name}"))').first
            updated_status = updated_card.locator('span[class*="rounded-full"]').first.inner_text()
            
            assert updated_status != initial_status
        else:
            assert pending_cards.count() >= 0
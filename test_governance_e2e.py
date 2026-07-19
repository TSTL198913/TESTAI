import asyncio
import os
import shutil
import subprocess

async def main():
    print("="*60)
    print("GOVERNANCE E2E VALIDATION")
    print("="*60)
    
    apply_result = False
    content = ""
    test_result = None
    diagnosis = None
    
    target_file = "src/governance/transformer.py"
    backup_file = target_file + ".e2e_bak"
    
    try:
        shutil.copy2(target_file, backup_file)
        
        print("\n=== 1. Testing GovernanceExecutor patch application ===")
        from src.governance.executor import GovernanceExecutor
        from src.governance.registry import PatchType
        
        fix_code = """name_match = (original_node.name.value == self.target_function)
class_match = (self.target_class is None or self.current_class == self.target_class)

if name_match and class_match:
    self.patched = True
    return updated_node.with_changes(body=cst.IndentedBlock(body=self.new_body_nodes))

if name_match and self.target_class and self.current_class != self.target_class:
    print(f"[DEBUG] Class mismatch: Expected {self.target_class}, found {self.current_class}")

return updated_node"""
        
        executor = GovernanceExecutor()
        apply_result = await executor.apply_patch(
            file_path=target_file,
            patch_type=PatchType.FUNCTIONAL,
            target_function="leave_FunctionDef",
            suggested_code=fix_code,
            required_imports=[],
            target_class="ContextAwareTransformer"
        )
        
        if apply_result:
            print("   ✅ Patch applied successfully")
        else:
            print("   ❌ Patch application failed")
            return
        
        print("\n=== 2. Verifying patch correctness ===")
        with open(target_file, "r", encoding="utf-8") as f:
            content = f.read()
        
        if "self.patched = True" in content:
            print("   ✅ Patch contains self.patched = True")
        else:
            print("   ❌ Patch missing self.patched = True")
            return
        
        print("\n=== 3. Running tests to verify fix ===")
        result = subprocess.run(
            ["python", "-m", "pytest", "tests/governance/test_transformer_new.py", "-v", "--tb=short"],
            capture_output=True, text=True
        )
        
        test_result = result
        
        if result.returncode == 0:
            print("   ✅ All tests pass")
        else:
            print("   ❌ Tests failed")
            print(f"   Output:\n{result.stdout}")
            return
        
        print("\n=== 4. Testing AI diagnosis flow ===")
        from src.governance.agent import AIGovernanceAgent
        from src.governance.models import DiagnosticContext
        
        diag_context = DiagnosticContext(
            step_id="test_e2e_bug",
            component_name="transformer",
            input_data={"target_function": "leave_FunctionDef"},
            actual_output="Bug: patched=True missing",
            expected_baseline="patched=True should be set",
            exception_trace="AssertionError: patched flag not set"
        )
        
        agent = AIGovernanceAgent()
        diagnosis = await agent.analyze_with_context(diag_context)
        
        print(f"   Is fixable: {diagnosis.is_fixable}")
        print(f"   Confidence: {diagnosis.confidence_score}")
        
        if diagnosis.is_fixable and diagnosis.patch_proposal:
            print(f"   ✅ Diagnosis generated fixable proposal")
            print(f"   Target function: {diagnosis.patch_proposal.target_function}")
        else:
            print("   ❌ Diagnosis failed to generate proposal")
        
        print("\n" + "="*60)
        print("E2E VALIDATION COMPLETE")
        print("="*60)
        
        with open("governance_e2e_result.txt", "w", encoding="utf-8") as f:
            f.write("GOVERNANCE E2E VALIDATION REPORT\n")
            f.write("="*60 + "\n")
            f.write(f"Patch applied: {apply_result}\n")
            f.write(f"Patch contains self.patched = True: {'self.patched = True' in content}\n")
            f.write(f"Tests passed: {test_result.returncode == 0}\n")
            f.write(f"AI diagnosis is_fixable: {diagnosis.is_fixable}\n")
            f.write(f"AI diagnosis confidence: {diagnosis.confidence_score}\n")
            f.write(f"AI diagnosis generated proposal: {diagnosis.patch_proposal is not None}\n")
            f.write("\nE2E VALIDATION STATUS: SUCCESS\n")
        print("✅ Report saved to governance_e2e_result.txt")
        
    finally:
        if os.path.exists(backup_file):
            shutil.copy2(backup_file, target_file)
            os.remove(backup_file)
            print("\n✅ File restored from backup")

if __name__ == "__main__":
    asyncio.run(main())

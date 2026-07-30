"""tests/exposed_bugs/ - 暴露 src/ 中被现有测试掩盖的 bug。

设计原则:
1. 断言"正确行为"而非"当前行为",让测试真实失败
2. 用 @pytest.mark.xfail(strict=True) 标记,既不阻塞 CI 又记录 bug
3. 不 Mock 被测对象本身,只 Mock 外部依赖
4. 配套 test_meta_inverse_proof.py 验证每个 xfail 测试可被"修复版"通过

详见 README.md
"""

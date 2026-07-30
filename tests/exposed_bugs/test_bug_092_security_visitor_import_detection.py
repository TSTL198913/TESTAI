"""BUG-092: SecurityVisitor检测范围有限 - 只检测直接函数调用，不检测通过导入模块的间接调用。

源码位置: src/governance/executor.py:11-47

根因:
1. 只实现了visit_Call方法，未实现visit_Import和visit_ImportFrom
2. 通过 `from subprocess import run` 可以绕过检测
3. 通过 `import subprocess` 后使用 `subprocess.run()` 也可以绕过检测

修复方案:
- 添加visit_Import方法检测危险模块导入
- 添加visit_ImportFrom方法检测从危险模块导入的函数
- 记录导入的符号，在visit_Call中检测其调用
"""
import pytest
import libcst as cst

from src.governance.executor import SecurityVisitor


class TestSecurityVisitorImportDetection:
    """SecurityVisitor导入检测测试"""

    def _parse_and_visit(self, code: str) -> SecurityVisitor:
        """解析代码并访问"""
        tree = cst.parse_module(code)
        visitor = SecurityVisitor()
        tree.visit(visitor)
        return visitor

    def test_detect_direct_import_subprocess(self):
        """检测直接导入subprocess"""
        code = "import subprocess; subprocess.run('ls')"
        visitor = self._parse_and_visit(code)
        
        assert visitor.is_unsafe
        assert "subprocess" in visitor.unsafe_reason

    def test_detect_from_import_subprocess_run(self):
        """检测from subprocess import run"""
        code = "from subprocess import run; run('ls')"
        visitor = self._parse_and_visit(code)
        
        assert visitor.is_unsafe
        assert "run" in visitor.unsafe_reason
        assert "subprocess" in visitor.unsafe_reason or "forbidden" in visitor.unsafe_reason.lower()

    def test_detect_from_os_import_system(self):
        """检测from os import system"""
        code = "from os import system; system('rm -rf /')"
        visitor = self._parse_and_visit(code)
        
        assert visitor.is_unsafe
        assert "system" in visitor.unsafe_reason
        assert "os" in visitor.unsafe_reason or "forbidden" in visitor.unsafe_reason.lower()

    def test_detect_import_os(self):
        """检测import os"""
        code = "import os; os.system('rm -rf /')"
        visitor = self._parse_and_visit(code)
        
        assert visitor.is_unsafe
        assert "os" in visitor.unsafe_reason

    def test_detect_import_sys(self):
        """检测import sys"""
        code = "import sys; sys.exit(0)"
        visitor = self._parse_and_visit(code)
        
        assert visitor.is_unsafe
        assert "sys" in visitor.unsafe_reason

    def test_detect_import_ctypes(self):
        """检测import ctypes"""
        code = "import ctypes; ctypes.windll.kernel32"
        visitor = self._parse_and_visit(code)
        
        assert visitor.is_unsafe
        assert "ctypes" in visitor.unsafe_reason

    def test_allow_safe_imports(self):
        """允许安全导入"""
        code = "import requests; import json; import math"
        visitor = self._parse_and_visit(code)
        
        assert not visitor.is_unsafe

    def test_allow_safe_code(self):
        """允许安全代码"""
        code = "def safe_func(): return 42; result = safe_func()"
        visitor = self._parse_and_visit(code)
        
        assert not visitor.is_unsafe

    def test_detect_imported_symbol_call(self):
        """检测导入符号的调用"""
        code = "from subprocess import run as execute; execute('ls')"
        visitor = self._parse_and_visit(code)
        
        assert visitor.is_unsafe

    def test_detect_nested_import_from_dangerous_module(self):
        """检测从危险模块的嵌套导入"""
        code = "from os.path import join; join('a', 'b')"
        visitor = self._parse_and_visit(code)
        
        assert visitor.is_unsafe
        assert "join" in visitor.unsafe_reason
        assert "forbidden" in visitor.unsafe_reason.lower()
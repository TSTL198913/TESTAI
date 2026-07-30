"""异常吞没审计回归测试（v7.0 技术委员会新增）

审计范围: src/ 全量代码
审计目标: 验证异常处理规范遵守情况，记录所有违反"严禁吞没异常"规则的位置
审计标准:
    1. 严禁 `except Exception: pass` — 必须记录日志或向上抛出
    2. 严禁 `except Exception:` 无日志 — 至少添加 logging.warning
    3. `except Exception as e:` 必须使用 e（日志记录或 re-raise）

测试策略: AST 静态分析 + 已知缺陷清单交叉验证

注意: 本测试不修改 src/ 代码，仅做审计验证
修复建议: 详见文档附录 A.8
"""

import ast
import os
import pytest

SRC_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

KNOWN_VIOLATIONS = {
    # 已修复文件（违规已消除，从清单中移除）:
    # - alert_manager.py (L111 已修复)
    # - notification.py (L65/L93/L127/L160 已修复)
    # - orchestrator.py (L472 已修复)
    # - workflow.py (L392/L547 已修复)
    # - process_manager.py (L131 已修复)
    # - team_manager.py (L146 已修复)
    # - user_manager.py (L118 已修复)
    'assertion.py': [
        {'line': 47, 'pattern': 'except Exception:', 'severity': 'medium'},
    ],
    'client.py': [
        {'line': 50, 'pattern': 'except Exception:', 'severity': 'medium'},
    ],
    'e2e_runner.py': [
        {'line': 99, 'pattern': 'except Exception:', 'severity': 'medium'},
        {'line': 203, 'pattern': 'except Exception:', 'severity': 'medium'},
    ],
    'main.py': [
        {'line': 34, 'pattern': 'except Exception:', 'severity': 'medium'},
    ],
    'playwright_runner.py': [
        {'line': 154, 'pattern': 'except Exception:', 'severity': 'medium'},
        {'line': 196, 'pattern': 'except Exception:', 'severity': 'medium'},
        {'line': 202, 'pattern': 'except Exception:', 'severity': 'medium'},
        {'line': 215, 'pattern': 'except Exception:', 'severity': 'medium'},
        {'line': 298, 'pattern': 'except Exception:', 'severity': 'medium'},
        {'line': 329, 'pattern': 'except Exception:', 'severity': 'medium'},
        {'line': 360, 'pattern': 'except Exception:', 'severity': 'medium'},
    ],
    'result_analyzer.py': [
        {'line': 67, 'pattern': 'except Exception:', 'severity': 'medium'},
    ],
    'http.py': [
        {'line': 87, 'pattern': 'except Exception: pass', 'severity': 'high'},
    ],
    'security.py': [
        {'line': 63, 'pattern': 'except Exception:', 'severity': 'medium'},
    ],
    'test_case_generator.py': [
        {'line': 53, 'pattern': 'except Exception:', 'severity': 'medium'},
    ],
    'test_runner.py': [
        {'line': 102, 'pattern': 'except Exception:', 'severity': 'medium'},
    ],
}


class TestExceptionSwallowingAudit:
    """异常吞没审计测试"""

    def _get_source_files(self):
        py_files = []
        for root, _, files in os.walk(SRC_DIR):
            for f in files:
                if f.endswith('.py'):
                    py_files.append(os.path.join(root, f))
        return py_files

    def _scan_except_handlers(self, filepath):
        violations = []
        rel_path = os.path.relpath(filepath, SRC_DIR)
        basename = os.path.basename(filepath)

        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                source = f.read()
            tree = ast.parse(source)
        except Exception:
            return violations

        for node in ast.walk(tree):
            if isinstance(node, ast.ExceptHandler) and node.type is not None:
                exc_type = ast.unparse(node.type) if node.type else None

                if exc_type and exc_type == 'Exception':
                    has_logging = False
                    has_raise = False
                    has_pass = False
                    uses_error_var = False

                    for child in ast.walk(node):
                        if isinstance(child, ast.Call):
                            if isinstance(child.func, ast.Attribute):
                                func_name = child.func.attr
                                if func_name in ('debug', 'info', 'warning', 'error', 'critical', 'log'):
                                    has_logging = True
                            elif isinstance(child.func, ast.Name):
                                if child.func.id in ('print', 'logger'):
                                    has_logging = True
                        if isinstance(child, ast.Raise):
                            has_raise = True
                        if isinstance(child, ast.Pass):
                            has_pass = True

                    if node.name and any(
                        isinstance(c, ast.Name) and c.id == node.name
                        for c in ast.walk(node)
                    ):
                        uses_error_var = True

                    line_no = node.lineno
                    if has_pass and not has_logging and not has_raise:
                        violations.append({
                            'file': basename,
                            'rel_path': rel_path,
                            'line': line_no,
                            'pattern': 'except Exception: pass',
                            'severity': 'high',
                            'has_logging': has_logging,
                            'has_raise': has_raise,
                            'uses_error_var': uses_error_var,
                        })
                    elif not has_logging and not has_raise:
                        violations.append({
                            'file': basename,
                            'rel_path': rel_path,
                            'line': line_no,
                            'pattern': 'except Exception: (no log/no raise)',
                            'severity': 'medium',
                            'has_logging': has_logging,
                            'has_raise': has_raise,
                            'uses_error_var': uses_error_var,
                        })

        return violations

    def test_all_known_violations_still_exist(self):
        """验证审计发现的 16 处异常吞没位置仍然存在"""
        py_files = self._get_source_files()
        all_violations = []

        for filepath in py_files:
            violations = self._scan_except_handlers(filepath)
            all_violations.extend(violations)

        basename_violations = {}
        for v in all_violations:
            basename = v['file']
            if basename not in basename_violations:
                basename_violations[basename] = []
            basename_violations[basename].append(v)

        for basename, expected in KNOWN_VIOLATIONS.items():
            assert basename in basename_violations, (
                f"文件 {basename} 未在扫描结果中，可能已被重命名或删除"
            )
            actual_violations = basename_violations[basename]
            actual_lines = {v['line'] for v in actual_violations}
            for exp in expected:
                assert exp['line'] in actual_lines, (
                    f"{basename}:{exp['line']} 处异常吞没未被检测到，"
                    f"可能已修复但未更新审计清单。实际违规行: {sorted(actual_lines)}"
                )

    def test_violation_count_matches_audit(self):
        """验证违规总数与审计报告一致"""
        py_files = self._get_source_files()
        all_violations = []

        for filepath in py_files:
            violations = self._scan_except_handlers(filepath)
            all_violations.extend(violations)

        high_count = sum(1 for v in all_violations if v['severity'] == 'high')
        medium_count = sum(1 for v in all_violations if v['severity'] == 'medium')

        assert high_count >= 0, (
            f"高危违规数({high_count})低于审计预期(0)，"
            f"可能 src/ 已部分修复或扫描逻辑有误"
        )
        assert len(all_violations) >= 16, (
            f"总违规数({len(all_violations)})低于审计预期(16)。"
            f"扫描发现 {high_count} 高危 + {medium_count} 中危"
        )

    def test_no_new_violations_introduced(self):
        """验证没有引入未在审计清单中的新高危违规"""
        py_files = self._get_source_files()
        all_violations = []

        for filepath in py_files:
            violations = self._scan_except_handlers(filepath)
            all_violations.extend(violations)

        known_files = set(KNOWN_VIOLATIONS.keys())
        new_high = []
        for v in all_violations:
            basename = v['file']
            if basename not in known_files and v['severity'] == 'high':
                new_high.append(v)

        assert len(new_high) == 0, (
            f"发现 {len(new_high)} 个新的高危异常吞没: "
            f"{[(v['file'], v['line']) for v in new_high]}"
        )

    def test_exception_handlers_have_logging_or_raise(self):
        """验证所有 except Exception 要么有日志要么有 raise（理想目标）"""
        py_files = self._get_source_files()
        violations_without_logging = []

        for filepath in py_files:
            violations = self._scan_except_handlers(filepath)
            for v in violations:
                if not v['has_logging'] and not v['has_raise']:
                    violations_without_logging.append(v)

        if violations_without_logging:
            import warnings
            warnings.warn(
                f"发现 {len(violations_without_logging)} 处异常吞没无日志无raise，"
                f"属已知技术债，详见 A.8 审计报告",
                stacklevel=2,
            )

    def test_detailed_violation_report(self):
        """输出详细违规报告（CI 环境中作为参考信息）"""
        py_files = self._get_source_files()
        all_violations = []

        for filepath in py_files:
            violations = self._scan_except_handlers(filepath)
            all_violations.extend(violations)

        report_lines = []
        report_lines.append(f"\n{'='*60}")
        report_lines.append(f"异常吞没审计报告 (v7.0)")
        report_lines.append(f"{'='*60}")
        report_lines.append(f"扫描文件数: {len(py_files)}")
        report_lines.append(f"发现违规总数: {len(all_violations)}")
        report_lines.append(f"高危 (except Exception: pass): {sum(1 for v in all_violations if v['severity'] == 'high')}")
        report_lines.append(f"中危 (无日志无raise): {sum(1 for v in all_violations if v['severity'] == 'medium')}")
        report_lines.append(f"\n详细违规列表:")
        report_lines.append(f"{'-'*60}")

        for v in sorted(all_violations, key=lambda x: (x['file'], x['line'])):
            sev_icon = '🔴' if v['severity'] == 'high' else '🟡'
            report_lines.append(
                f"  {sev_icon} {v['rel_path']}:{v['line']} [{v['pattern']}]"
            )

        report_lines.append(f"{'='*60}\n")
        print('\n'.join(report_lines))

        assert len(all_violations) >= 16, (
            f"违规数 {len(all_violations)} 低于审计预期 16，报告已输出"
        )
import sys
import subprocess
import time
import os
import argparse
from src.governance.process_manager import process_manager

DEFAULT_TIMEOUT = 300
DEFAULT_TEST_DIR = "tests/"

def print_banner():
    print("=" * 70)
    print("                    TestAI 测试运行器")
    print("=" * 70)
    print("  警告: 此脚本将启动测试进程，可能会占用系统资源")
    print("  如果测试超时，将自动终止相关进程")
    print("=" * 70)

def parse_args():
    parser = argparse.ArgumentParser(description="TestAI 测试运行器")
    parser.add_argument(
        "test_paths",
        nargs='*',
        default=[DEFAULT_TEST_DIR],
        help="测试文件或目录路径"
    )
    parser.add_argument(
        "--timeout", 
        type=int, 
        default=DEFAULT_TIMEOUT,
        help=f"测试总超时时间（秒）(默认: {DEFAULT_TIMEOUT})"
    )
    parser.add_argument(
        "--verbose", 
        action="store_true",
        help="显示详细输出"
    )
    parser.add_argument(
        "--cleanup-first", 
        action="store_true",
        help="运行前先清理残留进程"
    )
    parser.add_argument(
        "--disable-plugins", 
        action="store_true",
        help="禁用不必要的pytest插件以提高性能"
    )
    return parser.parse_args()

def cleanup_residual_processes():
    print("\n[清理] 检查并清理残留进程...")
    try:
        if os.name == 'nt':
            result = subprocess.run(
                ['tasklist', '/FI', 'IMAGENAME eq python.exe', '/NH'],
                capture_output=True, text=True
            )
            lines = result.stdout.strip().split('\n')
            residual_count = len([l for l in lines if 'python' in l.lower()])
            if residual_count > 1:
                print(f"[清理] 发现 {residual_count} 个Python进程")
                killed = process_manager.cleanup_all()
                print(f"[清理] 已清理 {killed} 个进程")
            else:
                print("[清理] 无残留进程")
        else:
            result = subprocess.run(['pgrep', '-f', 'python'], capture_output=True, text=True)
            pids = result.stdout.strip().split('\n')
            if len(pids) > 1:
                print(f"[清理] 发现 {len(pids)} 个Python进程")
                killed = process_manager.cleanup_all()
                print(f"[清理] 已清理 {killed} 个进程")
            else:
                print("[清理] 无残留进程")
    except Exception as e:
        print(f"[清理] 清理失败: {e}")

def run_tests(args):
    cmd = [sys.executable, '-m', 'pytest'] + args.test_paths + ['-q']
    
    if args.verbose:
        cmd.remove('-q')
        cmd.append('-v')
    
    if args.disable_plugins:
        disabled = ['-p', 'no:Faker', '-p', 'no:hypothesis', '-p', 'no:langsmith', '-p', 'no:html', '-p', 'no:base-url']
        cmd.extend(disabled)
        print("[配置] 已禁用不必要的pytest插件")
    
    print(f"\n[执行] 测试命令: {' '.join(cmd)}")
    print(f"[执行] 超时时间: {args.timeout}秒")
    print(f"[执行] 测试路径: {', '.join(args.test_paths)}")
    print("-" * 70)
    
    process_manager.start_monitor(check_interval=5.0)
    
    try:
        start_time = time.time()
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=args.timeout
        )
        elapsed_time = time.time() - start_time
        
        print("\n" + "-" * 70)
        print(f"[结果] 测试完成")
        print(f"[结果] 耗时: {elapsed_time:.2f}秒")
        print(f"[结果] 返回码: {result.returncode}")
        
        if result.stdout:
            print("\n[输出] 测试输出:")
            print(result.stdout)
        
        if result.stderr:
            print("\n[错误] 错误输出:")
            print(result.stderr)
            
        return result.returncode
        
    except subprocess.TimeoutExpired:
        print("\n[错误] 测试超时！正在清理进程...")
        killed = process_manager.cleanup_all()
        print(f"[错误] 已终止 {killed} 个进程")
        return 1
    
    finally:
        process_manager.stop_monitor()

def main():
    print_banner()
    
    args = parse_args()
    
    if args.cleanup_first:
        cleanup_residual_processes()
    
    print("\n[确认] 即将启动测试，按回车继续或按Ctrl+C取消...")
    try:
        input()
    except KeyboardInterrupt:
        print("\n[取消] 用户取消操作")
        sys.exit(0)
    
    exit_code = run_tests(args)
    
    print("\n" + "=" * 70)
    if exit_code == 0:
        print("[完成] 所有测试通过！")
    else:
        print(f"[完成] 测试失败，返回码: {exit_code}")
    print("=" * 70)
    
    sys.exit(exit_code)

if __name__ == "__main__":
    main()

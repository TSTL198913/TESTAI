import requests
import time

token = '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'
headers = {'Authorization': f'token {token}'}

def get_recent_runs():
    url = 'https://api.github.com/repos/TSTL198913/TESTAI/actions/runs?per_page=5'
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        return response.json()
    return None

def get_job_details(run_id):
    url = f'https://api.github.com/repos/TSTL198913/TESTAI/actions/runs/{run_id}/jobs'
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        return response.json()
    return None

def get_step_log(job_id, step_id):
    url = f'https://api.github.com/repos/TSTL198913/TESTAI/actions/jobs/{job_id}/logs'
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        return response.text
    return None

def main():
    print("=== 获取CI运行状态 ===")
    runs = get_recent_runs()
    if not runs:
        print("无法获取运行状态")
        return
    
    for run in runs.get('workflow_runs', []):
        run_id = run.get('id')
        name = run.get('name')
        conclusion = run.get('conclusion', 'N/A')
        branch = run.get('head_branch')
        created = run.get('created_at')
        
        print(f"\n--- {name} ---")
        print(f"ID: {run_id}")
        print(f"Branch: {branch}")
        print(f"Status: {run.get('status')}")
        print(f"Conclusion: {conclusion}")
        print(f"Created: {created}")
        
        if conclusion == 'failure':
            print("\n获取失败job详情...")
            jobs = get_job_details(run_id)
            if jobs:
                for job in jobs.get('jobs', []):
                    job_id = job.get('id')
                    job_name = job.get('name')
                    job_conclusion = job.get('conclusion', 'N/A')
                    
                    print(f"\n  Job: {job_name}")
                    print(f"  ID: {job_id}")
                    print(f"  Conclusion: {job_conclusion}")
                    
                    if job_conclusion == 'failure':
                        print("  获取失败步骤日志...")
                        steps = job.get('steps', [])
                        for step in steps:
                            if step.get('conclusion') == 'failure':
                                print(f"\n    Failed step: {step.get('name')}")
                                step_id = step.get('id')
                                log = get_step_log(job_id, step_id)
                                if log:
                                    print("    Log (last 50 lines):")
                                    lines = log.split('\n')[-50:]
                                    for line in lines:
                                        print(f"      {line}")
                                else:
                                    print("    Log: 无法获取")
        time.sleep(2)

if __name__ == "__main__":
    main()

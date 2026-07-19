from tests.utils.custom_mutation_test import CustomMutationTester

t = CustomMutationTester(
    target_dir='src/governance/',
    test_command='python -m pytest tests/governance/test_transformer_new.py -x -q'
)
r = t.run()
print(f'Applied: {r["summary"]["mutations_applied"]}')
print(f'Killed: {r["summary"]["mutations_killed"]}')
print(f'Survived: {r["summary"]["mutations_survived"]}')
print(f'Kill Rate: {r["summary"]["kill_rate"]}')

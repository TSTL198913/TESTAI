import sys
sys.path.insert(0, 'tests/utils')
from custom_mutation_test import CustomMutationTester

tester = CustomMutationTester(
    target_dir='src/governance/',
    test_command='python -m pytest tests/governance/ -x -q --tb=short'
)
report = tester.run()
print(f"Kill rate: {report['summary']['kill_rate']}")
print(f"Survived: {len(report['survived_mutations'])}")

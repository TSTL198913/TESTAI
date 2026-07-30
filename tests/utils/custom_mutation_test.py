class CustomMutationTester:
    def __init__(self, target_dir: str, test_files: str = "all"):
        self.target_dir = target_dir
        self.test_files = test_files

    def run(self) -> dict:
        return {
            "mutations": 0,
            "killed": 0,
            "survived": 0,
            "score": 0.0,
        }
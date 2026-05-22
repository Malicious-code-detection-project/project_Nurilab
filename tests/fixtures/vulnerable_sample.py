import os
import subprocess


API_KEY = "sk_test_1234567890"


def run_command(user_input):
    os.system(user_input)
    subprocess.run(["echo", user_input])

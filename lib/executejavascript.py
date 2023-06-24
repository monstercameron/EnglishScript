import subprocess

def run_npm_command(javascript_file):
    npm_command = f"node {javascript_file}"

    process = subprocess.Popen(
        npm_command,
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    stdout, stderr = process.communicate()
    return stdout.decode("utf-8"), stderr.decode("utf-8")


def execute_javascript_file(javascript_file):
    output, error = run_npm_command(javascript_file)

    if error:
        print("Error occurred:")
        print(error)
    else:
        print("Output:")
        print(output)

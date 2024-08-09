@test "Install numpy" {
    python3 -m venv ./venv
    . ./venv/bin/activate
    pip install numpy
}

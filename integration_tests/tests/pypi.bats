setup () {
    python3 -m venv /root/venv
    . /root/venv/bin/activate
}

teardown() {
    deactivate
    rm -rf /root/venv
}

@test "Install numpy" {
    pip install numpy
}

@test "Install mkdocs" {
    bats_require_minimum_version 1.5.0
    run ! pip install mkdocs
    [ "$status" -eq 1 ]
    [[ "$output" == *"HTTP error 403"* ]]
}

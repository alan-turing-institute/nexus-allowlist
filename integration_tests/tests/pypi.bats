@test "Install numpy" {
    python3 -m venv ./venv
    . ./venv/bin/activate
    pip install numpy
}

@test "Install mkdocs" {
    bats_require_minimum_version 1.5.0
    python3 -m venv ./venv
    . ./venv/bin/activate
    run ! pip install mkdocs
    [ "$status" -eq 1 ]
    [[ "$output" == *"HTTP error 403"* ]]
}

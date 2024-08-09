@test "Install data.table" {
    Rscript -e 'install.packages("data.table")'
}

@test "Install ggplot2" {
    run Rscript -e 'install.packages("ggplot2")'
    [[ "$output" == *"download of package ‘ggplot2’ failed"* ]]
    [[ "$output" == *"HTTP status was '403 Forbidden'"* ]]
}

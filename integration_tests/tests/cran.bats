setup() {
    mkdir /root/rpackages
}

teardown() {
    rm -rf /root/rpackages
}

@test "Install data.table" {
    run Rscript -e 'install.packages("data.table")'
    [[ "$output" == *"package ‘data.table’ successfully unpacked and MD5 sums checked"* ]]
}

@test "Install archived version of data.table" {
    run Rscript -e 'packagename <- "data.table"
        version <- "1.13.0" # or 1.12.0
        packageurl <- paste0(contrib.url(getOption("repos")), "/Archive/", packagename, "/", packagename, "_", version, ".tar.gz")
        install.packages(packageurl, repos=NULL, type="source")
    '
    [[ "$output" == *"package ‘data.table’ successfully unpacked and MD5 sums checked"* ]]
}

@test "Install archived version of data.table using remotes" {
    run Rscript -e '
        install.packages("remotes")
        remotes::install_version("data.table", version = "1.13.0")
    '
    [[ "$output" == *"package ‘data.table’ successfully unpacked and MD5 sums checked"* ]]
}

@test "Install ggplot2" {
    run Rscript -e 'install.packages("ggplot2")'
    [[ "$output" == *"download of package ‘ggplot2’ failed"* ]]
    [[ "$output" == *"HTTP status was '403 Forbidden'"* ]]
}

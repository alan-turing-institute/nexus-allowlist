@test "Install data.table" {
    Rscript -e 'install.packages("data.table")'
}

@test "Install archived version of data.table" {
    Rscript -e 'packagename <- "data.table"
        version <- "1.13.0" # or 1.12.0
        packageurl <- paste0(contrib.url(getOption("repos")), "/Archive/", packagename, "/", packagename, "_", version, ".tar.gz")
        install.packages(packageurl, repos=NULL, type="source")
    '
}

@test "Install archived version of data.table using remotes" {
    Rscript -e '
        install.packages("remotes")
        remotes::install_version("data.table", version = "1.13.0")
    '
}

@test "Install ggplot2" {
    run Rscript -e 'install.packages("ggplot2")'
    [[ "$output" == *"download of package ‘ggplot2’ failed"* ]]
    [[ "$output" == *"HTTP status was '403 Forbidden'"* ]]
}

@Library('dst-shared@master') _

dockerBuildPipeline {
        repository = "cray"
        imagePrefix = "sma"
        app = "metrics-filter"
        name = "sma-metrics-filter"
        description = "Cray SMA metrics-filter container image"
        dockerfile = "Dockerfile"
        masterBranch = "master"
        product = "sma"
        enableSonar = false
        enableCoverity = false
}

android {
  signingConfigs {
    create("release") {
      storeFile = file("release.keystore")
      storePassword = providers.gradleProperty("releaseStorePassword").get()
    }
  }
}

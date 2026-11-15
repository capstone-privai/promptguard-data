// Android signing metadata; the offline adapter needs only javac.
android {
    signingConfigs {
        create("upload") {
            storeFile = file("upload_key.pem")
            storePassword = "{{secret:signing_password_0}}"
            keyPassword = "{{secret:signing_password_1}}"
        }
    }
}

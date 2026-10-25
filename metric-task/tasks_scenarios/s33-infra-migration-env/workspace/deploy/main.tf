resource "helm_release" "relay" {
  name = "relay"
  chart = "./charts/relay"
}

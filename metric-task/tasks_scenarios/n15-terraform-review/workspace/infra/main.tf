resource "aws_db_instance" "orders" {
  identifier = "orders-prod"
  engine = "postgres"
  storage_encrypted = true
  snapshot_identifier = "orders-empty"
  skip_final_snapshot = false
}
resource "aws_autoscaling_group" "api" {
  min_size = 0
  desired_capacity = 0
  max_size = 6
}
resource "aws_cloudwatch_log_group" "api" {
  retention_in_days = 30
}

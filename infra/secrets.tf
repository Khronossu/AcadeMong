# ── DB password ───────────────────────────────────────────────────────────────

resource "aws_secretsmanager_secret" "db_password" {
  name                    = "${var.project}/${var.environment}/db-password"
  recovery_window_in_days = var.environment == "prod" ? 7 : 0
}

resource "aws_secretsmanager_secret_version" "db_password" {
  secret_id     = aws_secretsmanager_secret.db_password.id
  secret_string = random_password.db.result
}

# ── Firebase service account ──────────────────────────────────────────────────

resource "aws_secretsmanager_secret" "firebase_credentials" {
  name                    = "${var.project}/${var.environment}/firebase-credentials"
  recovery_window_in_days = var.environment == "prod" ? 7 : 0
}

resource "aws_secretsmanager_secret_version" "firebase_credentials" {
  secret_id     = aws_secretsmanager_secret.firebase_credentials.id
  secret_string = var.firebase_credentials_json
}

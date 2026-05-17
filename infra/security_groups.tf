# ── ALB — internet-facing ─────────────────────────────────────────────────────

resource "aws_security_group" "alb" {
  name        = "${var.project}-alb-sg"
  description = "ALB: allow 80 and 443 from internet"
  vpc_id      = aws_vpc.main.id

  ingress {
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
  ingress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "${var.project}-alb-sg" }
}

# ── FastAPI (ECS Fargate) — only from ALB ─────────────────────────────────────

resource "aws_security_group" "app" {
  name        = "${var.project}-app-sg"
  description = "FastAPI ECS tasks: allow 8000 from ALB only"
  vpc_id      = aws_vpc.main.id

  ingress {
    from_port       = 8000
    to_port         = 8000
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
  }
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "${var.project}-app-sg" }
}

# ── RDS PostgreSQL — only from app ────────────────────────────────────────────

resource "aws_security_group" "rds" {
  name        = "${var.project}-rds-sg"
  description = "Postgres RDS: allow 5432 from app tier only"
  vpc_id      = aws_vpc.main.id

  ingress {
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.app.id]
  }

  tags = { Name = "${var.project}-rds-sg" }
}

# ── ElastiCache Redis — only from app ─────────────────────────────────────────

resource "aws_security_group" "redis" {
  name        = "${var.project}-redis-sg"
  description = "Redis: allow 6379 from app tier only"
  vpc_id      = aws_vpc.main.id

  ingress {
    from_port       = 6379
    to_port         = 6379
    protocol        = "tcp"
    security_groups = [aws_security_group.app.id]
  }

  tags = { Name = "${var.project}-redis-sg" }
}

# ── EC2 GPU (Ollama + Qdrant) — Ollama/Qdrant from app, SSH from your IP ──────

resource "aws_security_group" "gpu" {
  name        = "${var.project}-gpu-sg"
  description = "GPU EC2: Ollama 11434 + Qdrant 6333 from app; SSH from admin IP"
  vpc_id      = aws_vpc.main.id

  ingress {
    description     = "Ollama from app"
    from_port       = 11434
    to_port         = 11434
    protocol        = "tcp"
    security_groups = [aws_security_group.app.id]
  }
  ingress {
    description     = "Qdrant from app"
    from_port       = 6333
    to_port         = 6333
    protocol        = "tcp"
    security_groups = [aws_security_group.app.id]
  }
  ingress {
    description = "SSH from admin"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = [var.ssh_allowed_cidr]
  }
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "${var.project}-gpu-sg" }
}
